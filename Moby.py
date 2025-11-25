
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 
import pandas as pd
import os
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby v24 ERP")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        c_logo, c_title = st.columns([1, 4])
        try: c_logo.image("logo.png", width=150)
        except: pass
        c_title.markdown("## 🔒 Area Riservata")
        c1, c2 = st.columns(2)
        u = c1.text_input("User")
        p = c2.text_input("Password", type="password")
        if st.button("Entra"):
            try: db = st.secrets["passwords"]
            except: db = {"admin": "admin"} 
            if u in db and db[u] == p:
                st.session_state.logged_in = True
                st.session_state.username = u
                st.rerun()
            else: st.error("Accesso Negato")
        st.stop()

check_login()

# --- 2. COSTANTI GEOMETRICHE ---
SPESSORE_LEGNO = 4.0 
SPESSORE_FERRO = 0.3 
DIAMETRO_FORO = 0.6 
OFFSET_LATERALI = 3.0
PESO_SPECIFICO_FERRO = 7.85 
PESO_SPECIFICO_LEGNO = 0.70 

VERSION = "v24 (Logic & Commercial)"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- UTILITY ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- 3. TEMPI & COSTI (DEFAULT EXPANDED) ---
DEFAULT_CONFIG = {
    # Costi Unitari
    "costo_ferro_kg": 2.0,
    "costo_legno_mq": 30.0, 
    "costo_ora_operaio": 35.0,
    "markup_totale": 2.5, # Ricarico Moltiplicatore
    
    # Tempi Standard (Giorni)
    "gg_ordine_ferro": 1,
    "gg_arrivo_lastra": 5,
    "gg_taglio_ferro": 1,
    "gg_verniciatura_ferro": 5,
    "gg_verniciatura_legno": 3, # Asciugatura inclusa
    "gg_attesa_corriere": 2, # Ritiro e smistamento
    
    # Lavorazioni (Minuti/Ore)
    "min_taglio_legno_pezzo": 5.0,
    "min_verniciatura_legno_mq": 20.0,
    "min_assemblaggio_mensola": 5.0, # Pre-assemblaggio inserti
    "min_preassemblaggio_struttura": 30.0, # Verifica in officina (totale)
    
    # Logistica Standard
    "ore_imballo_base": 1.0, # Sempre presente
    "ore_imballo_extra_spedizione": 2.0, # Solo se spedito
    "costo_imballo_materiale": 20.0,
    
    # Trasferta default
    "num_operai_trasferta": 2
}

def load_costs_config():
    if 'erp_config' not in st.session_state:
        if os.path.exists("erp_default.json"):
            try:
                with open("erp_default.json", "r") as f:
                    st.session_state.erp_config = json.load(f)
            except:
                st.session_state.erp_config = DEFAULT_CONFIG.copy()
        else:
            st.session_state.erp_config = DEFAULT_CONFIG.copy()

load_costs_config()

# --- 4. PDF ENGINE (AUTO-SCALING & LAYOUTS) ---
class PDFReport(FPDF):
    def __init__(self, project_name, colors, is_commercial=False):
        super().__init__()
        self.project_name = project_name
        self.colors = colors
        self.is_commercial = is_commercial
        
    def header(self):
        if self.is_commercial:
            # Header per Preventivo
            if os.path.exists("logo.png"):
                try: self.image("logo.png", 10, 8, 40)
                except: pass
            self.set_font('Arial', 'B', 16)
            self.cell(0, 10, 'PREVENTIVO', 0, 1, 'R')
            self.set_font('Arial', '', 10)
            self.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
            self.ln(20)
        else:
            # Header Tecnico
            self.set_font('Arial', 'B', 10)
            self.cell(0, 6, f'SCHEDA TECNICA: {self.project_name}', 0, 1, 'R')
            self.line(10, 15, 200, 15)
            self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'{COPYRIGHT} - Pagina ' + str(self.page_no()), 0, 0, 'C')

    def auto_scale(self, needed_width_mm, available_width_mm, max_scale=0.35):
        """Calcola la scala necessaria per far stare il disegno"""
        if needed_width_mm * max_scale > available_width_mm:
            return available_width_mm / needed_width_mm
        return max_scale

def generate_pdf_technical(project_name, parts_list, wood_data, iron_data, stats, cols_data, colors):
    pdf = PDFReport(project_name, colors, is_commercial=False)
    
    # 1. PROSPETTO FRONTALE
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "PROSPETTO FRONTALE", 0, 1)
    
    tot_width_cm = sum([c['w'] + (SPESSORE_FERRO*2) for c in cols_data])
    scale = pdf.auto_scale(tot_width_cm * 10, 180, 0.35) # *10 per convertire cm in mm approx nel disegno
    
    start_x = 20
    start_y = 60
    current_x = start_x
    
    pdf.line(10, start_y + 120, 200, start_y + 120) 
    for col in cols_data:
        h, w = col['h'] * scale, col['w'] * scale
        w_ferro = 0.3
        
        pdf.set_fill_color(50, 50, 50)
        pdf.rect(current_x, start_y + (120 - h), w_ferro, h, 'F') # SX
        
        pdf.set_fill_color(200, 180, 140)
        if col['mh']:
            for z in col['mh']:
                mz = z * scale
                pdf.rect(current_x + w_ferro, start_y + (120 - mz - (SPESSORE_LEGNO*scale)), w, (SPESSORE_LEGNO*scale), 'F')
        
        current_x += w + w_ferro
        pdf.set_fill_color(50, 50, 50)
        pdf.rect(current_x, start_y + (120 - h), w_ferro, h, 'F') # DX
        current_x += w_ferro + 0.5

    # 2. PIANTA (LANDSCAPE per spazio extra)
    pdf.add_page(orientation='L')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "PIANTA (VISTA DALL'ALTO)", 0, 1)
    
    # Auto-scale su larghezza landscape (297mm - margini = 270mm)
    scale_pianta = pdf.auto_scale(tot_width_cm * 10, 260, 0.65)
    
    start_x = 20
    start_y = 50
    current_y = start_y
    
    # Disegno pianta rotato visivamente o steso? Facciamo steso orizzontalmente
    # Qui disegniamo i moduli uno accanto all'altro
    curr_x_pianta = start_x
    for col in cols_data:
        w_mod = (col['w'] + (SPESSORE_FERRO*2)) * scale_pianta
        d_mod = col['d'] * scale_pianta
        
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(curr_x_pianta, start_y, w_mod, d_mod, 'D')
        
        # Quote
        pdf.set_font("Arial", '', 8)
        pdf.set_xy(curr_x_pianta, start_y - 5)
        pdf.cell(w_mod, 5, f"{col['w']:.0f}", 0, 0, 'C')
        pdf.set_xy(curr_x_pianta, start_y + d_mod + 2)
        pdf.cell(w_mod, 5, f"P: {col['d']:.0f}", 0, 0, 'C')
        
        curr_x_pianta += w_mod

    # 3. LISTA MATERIALI (Ritorniamo Portrait)
    pdf.add_page(orientation='P')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "DISTINTA BASE", 0, 1)
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, f"Peso Ferro: {stats['peso_ferro']:.1f} kg", 1)
    pdf.cell(50, 8, f"Peso Legno: {stats['peso_legno']:.1f} kg", 1)
    pdf.cell(50, 8, f"Totale: {stats['peso_tot']:.1f} kg", 1, 1)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "LISTA TAGLIO LEGNO", 0, 1)
    pdf.set_font("Arial", '', 9)
    if not wood_data.empty:
        for index, row in wood_data.iterrows():
            pdf.cell(100, 7, f"N. {row['Pezzi']} Pz - {row['Larghezza']:.0f} x {row['Profondità']:.0f} cm", 1, 1)

    return pdf.output(dest='S').encode('latin-1')

def generate_pdf_commercial(project_data, totals, client_data):
    pdf = PDFReport(project_data['project_name'], {}, is_commercial=True)
    pdf.add_page()
    
    # Info Cliente
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 5, "Spett.le:", 0, 1)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(100, 5, client_data['name'], 0, 1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 5, client_data['address'], 0, 1)
    pdf.ln(20)
    
    # Oggetto
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Oggetto: Fornitura Libreria Modulare {project_data['project_name']}", 0, 1)
    pdf.ln(5)
    
    # Descrizione
    pdf.set_font("Arial", '', 10)
    desc = f"Libreria composta da {project_data['num_colonne']} moduli.\n"
    desc += f"Finiture: Struttura in metallo verniciato {project_data['finish_iron']}, ripiani in legno {project_data['finish_wood']}."
    pdf.multi_cell(0, 6, desc)
    pdf.ln(10)
    
    # Tabella Prezzi Semplificata
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(140, 8, "Descrizione", 1, 0, 'L', True)
    pdf.cell(40, 8, "Importo", 1, 1, 'R', True)
    
    pdf.cell(140, 10, "Fornitura Struttura e Ripiani su misura", 1, 0)
    pdf.cell(40, 10, f"E {totals['price_ex_vat'] - totals['logistics_price']:.2f}", 1, 1, 'R')
    
    if totals['logistics_price'] > 0:
        label_log = "Spedizione con Corriere" if totals['logistics_type'] == "corriere" else "Trasporto e Montaggio in loco"
        pdf.cell(140, 10, label_log, 1, 0)
        pdf.cell(40, 10, f"E {totals['logistics_price']:.2f}", 1, 1, 'R')
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(140, 10, "TOTALE IMPONIBILE", 0, 0, 'R')
    pdf.cell(40, 10, f"E {totals['price_ex_vat']:.2f}", 1, 1, 'R')
    
    pdf.cell(140, 10, "IVA (22%)", 0, 0, 'R')
    pdf.cell(40, 10, f"E {totals['vat']:.2f}", 1, 1, 'R')
    
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(140, 12, "TOTALE FORNITURA", 1, 0, 'R', True)
    pdf.cell(40, 12, f"E {totals['price_total']:.2f}", 1, 1, 'R', True)
    
    # Reset colore
    pdf.set_text_color(0, 0, 0)
    pdf.ln(15)
    
    # Tempistiche
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(50, 6, "Tempi di Consegna stimati:", 0, 0)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"{totals['days_total']} giorni lavorativi dalla conferma ordine", 0, 1)
    if totals['delivery_date']:
        pdf.cell(0, 6, f"(Data prevista approssimativa: {totals['delivery_date']})", 0, 1)

    return pdf.output(dest='S').encode('latin-1')

# --- 4. DXF & 3D (Rimaniamo snelli) ---
def create_dxf_doc():
    doc = ezdxf.new()
    return doc
# (Ometto funzioni DXF e 3D identiche alla v23 per brevità, assumile presenti o copiale dalla vecchia versione se serve)
def add_stl(x,y,z,dx,dy,dz):
    v = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],[x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]]
    idx = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[2,3,7],[2,7,6],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    for t in idx: stl_triangles.append((v[t[0]],v[t[1]],v[t[2]]))
def draw(x,y,z,dx,dy,dz,col,name):
    add_stl(x,y,z,dx,dy,dz)
    xv, yv, zv = [x, x+dx, x+dx, x]*2, [y, y, y+dy, y+dy]*2, [z]*4 + [z+dz]*4
    I,J,K = [0,0,4,4,0,0,2,2,3,3,1,1], [1,2,5,6,1,5,3,7,0,4,2,6], [2,3,6,7,5,4,7,6,4,7,6,5]
    return go.Mesh3d(x=xv, y=yv, z=zv, i=I, j=J, k=K, color=col, opacity=1, flatshading=True, name=name)
def get_bin_stl(tris):
    out = io.BytesIO(); out.write(b'\0'*80 + struct.pack('<I', len(tris)))
    for p in tris: out.write(struct.pack('<ffffffffffffH', 0,0,0, *p[0], *p[1], *p[2], 0))
    return out.getvalue()

# --- 5. LOGICA PREVENTIVATORE ---
def calculate_quote(stats, user_inputs):
    cfg = st.session_state.erp_config
    
    # 1. COSTI MATERIALI VIVI
    cost_ferro = stats['peso_ferro'] * cfg['costo_ferro_kg']
    cost_legno_mq = (stats['peso_legno'] / PESO_SPECIFICO_LEGNO / SPESSORE_LEGNO * 1000) # stima mq
    # Meglio usare i mq calcolati prima se possibile, qui approssimo per non complicare il passaggio dati
    # Recupero metri totali da wood_list se disponibile, altrimenti stima
    cost_legno = stats['mq_legno'] * cfg['costo_legno_mq']
    cost_mat_tot = cost_ferro + cost_legno
    
    # 2. TEMPI & COSTI LAVORAZIONE (PARALLELO)
    # Strada Ferro
    days_iron = 0
    if not user_inputs['stock_iron']:
        days_iron += cfg['gg_ordine_ferro'] + cfg['gg_arrivo_lastra']
    days_iron += cfg['gg_taglio_ferro'] + cfg['gg_verniciatura_ferro']
    
    # Strada Legno
    days_wood = 0
    # Taglio
    mins_cut_wood = stats['num_pezzi_legno'] * cfg['min_taglio_legno_pezzo']
    # Verniciatura
    mins_varnish_wood = stats['mq_legno'] * cfg['min_verniciatura_legno_mq']
    
    hrs_wood_prod = (mins_cut_wood + mins_varnish_wood) / 60.0
    days_wood_work = (hrs_wood_prod / 8.0) # Giorni lavorativi effettivi
    days_wood = days_wood_work + cfg['gg_verniciatura_legno'] # Aggiungo asciugatura
    
    # Punto di Incontro
    days_production = max(days_iron, days_wood)
    
    # Assemblaggio Interno (Premontaggio)
    mins_pre_shelves = stats['num_pezzi_legno'] * cfg['min_assemblaggio_mensola']
    mins_pre_struct = user_inputs['num_cols'] * cfg['min_preassemblaggio_struttura']
    hrs_pre_assembly = (mins_pre_shelves + mins_pre_struct) / 60.0
    
    cost_labor_prod = (hrs_wood_prod + hrs_pre_assembly) * cfg['costo_ora_operaio']
    
    # 3. LOGISTICA
    log_cost = 0.0
    log_days = 0
    hrs_packing = cfg['ore_imballo_base'] # Base
    
    if user_inputs['logistics_type'] == "corriere":
        hrs_packing += cfg['ore_imballo_extra_spedizione']
        log_cost += user_inputs['costo_corriere']
        log_days += cfg['gg_attesa_corriere'] + user_inputs['gg_viaggio_corriere']
    else:
        # Montaggio Nostro
        # Ore totali = (Viaggio A/R + Montaggio) * Persone
        trip_time = user_inputs['ore_viaggio']
        install_time = user_inputs['ore_montaggio']
        people = user_inputs['num_operai']
        
        total_man_hours_site = (trip_time + install_time) * people
        log_cost += total_man_hours_site * cfg['costo_ora_operaio']
        log_days += 1 # Consideriamo 1 giorno per la missione
    
    cost_packing = (hrs_packing * cfg['costo_ora_operaio']) + cfg['costo_imballo_materiale']
    
    # 4. TOTALI
    cost_total_production = cost_mat_tot + cost_labor_prod + cost_packing
    
    # APPLICAZIONE MARKUP (Sul costo produzione + logistica se interna?
    # Solitamente si fa markup su produzione e poi logistica a parte o markuppata meno.
    # Qui seguiamo richiesta: Ricarico su tutto)
    
    base_for_markup = cost_total_production + log_cost
    price_final_ex_vat = base_for_markup * cfg['markup_totale']
    
    vat = price_final_ex_vat * 0.22
    
    # Data Consegna
    final_days = days_production + log_days + 1 # +1 margine
    del_date = user_inputs['start_date'] + timedelta(days=int(final_days))
    
    return {
        "cost_mat": cost_mat_tot,
        "cost_prod": cost_total_production,
        "logistics_type": user_inputs['logistics_type'],
        "logistics_price": log_cost * cfg['markup_totale'], # Prezzo vendita logistica
        "price_ex_vat": price_final_ex_vat,
        "vat": vat,
        "price_total": price_final_ex_vat + vat,
        "days_total": int(final_days),
        "delivery_date": del_date.strftime("%d/%m/%Y")
    }

# --- 6. SIDEBAR & DATA ---
with st.sidebar:
    # CORREZIONE: Usiamo un if/else esplicito per evitare che stampi il codice a video
    if os.path.exists("logo.png"):
        st.image("logo.png", width=150)
    else:
        st.title("MOBY ERP")
        
    st.markdown("---")
    
    st.session_state.setdefault('project_name', "Progetto_01")
    st.session_state['project_name'] = st.text_input("Nome Progetto", st.session_state['project_name'])
    
    st.subheader("Anagrafica Cliente")
    st.session_state.setdefault('client_name', "")
    st.session_state.setdefault('client_address', "")
    st.session_state['client_name'] = st.text_input("Nome / Ragione Sociale", st.session_state['client_name'])
    st.session_state['client_address'] = st.text_input("Indirizzo", st.session_state['client_address'])
    
    st.subheader("Finiture")
    st.session_state.setdefault('finish_wood', "Rovere")
    st.session_state.setdefault('finish_iron', "Nero")
    st.session_state['finish_wood'] = st.text_input("Legno", st.session_state['finish_wood'])
    st.session_state['finish_iron'] = st.text_input("Ferro", st.session_state['finish_iron'])
    
    st.markdown("---")
    st.subheader("Configurazione Moduli")
    num_colonne = st.number_input("N. Moduli", 1, 10, 2)

    dati_colonne = []
    wood_list = []
    iron_stats_list = []
    
    for i in range(num_colonne):
        with st.expander(f"Modulo {chr(65+i)}"):
            w = st.number_input(f"L (cm)", 30, 200, 60, key=f"w{i}")
            h = st.number_input(f"H (cm)", 50, 400, 240, key=f"h{i}")
            d = st.number_input(f"P (cm)", 20, 100, 30, key=f"d{i}")
            r = st.number_input(f"Mensole", 1, 20, 5, key=f"r{i}")
            step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
            mh = [n*step for n in range(r)]
            dati_colonne.append({"w":w, "h":h, "d":d, "r":r, "mh":mh})
            for _ in range(r): wood_list.append({"w":w, "d":d})
            iron_stats_list.append({"h":h, "d":d})

    # 3D
    fig = go.Figure()
    cx = 0
    for dc in dati_colonne:
        fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', 'Ferro'))
        cx += SPESSORE_FERRO
        for z in dc["mh"]:
            fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, '#D2B48C', 'Legno'))
        cx += dc["w"]
        fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', 'Ferro'))
        cx += SPESSORE_FERRO
    
    fig.update_layout(scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), margin=dict(l=0,r=0,t=0,b=0), height=300)

# --- 7. UI MAIN TABS ---
tab_3d, tab_prev = st.tabs(["🎥 CONFIGURATORE 3D", "💰 PREVENTIVATORE & PRODUZIONE"])

with tab_3d:
    st.plotly_chart(fig, use_container_width=True)
    st.info("Configura i moduli nella barra laterale sinistra.")

with tab_prev:
    # CALCOLO DATI FISICI BASE
    vol_ferro = sum([c['h']*c['d']*SPESSORE_FERRO*2 for c in dati_colonne]) # approx
    peso_ferro = (vol_ferro * PESO_SPECIFICO_FERRO) / 1000.0
    
    mq_legno = sum([(w['w']*w['d'])/10000.0 for w in wood_list])
    vol_legno = mq_legno * SPESSORE_LEGNO 
    peso_legno = (vol_legno * PESO_SPECIFICO_LEGNO * 10) # fix unita
    
    stats_base = {
        "peso_ferro": peso_ferro, 
        "peso_legno": peso_legno, 
        "peso_tot": peso_ferro+peso_legno, 
        "mq_legno": mq_legno,
        "num_pezzi_legno": len(wood_list)
    }

    st.markdown("### 🛠️ Pannello Controllo Produzione")
    
    col_input1, col_input2, col_input3 = st.columns(3)
    
    with col_input1:
        st.markdown("#### 1. Tempistiche & Stock")
        date_start = st.date_input("Data Conferma Ordine", datetime.now())
        st.caption("Disponibilità Magazzino:")
        stock_iron = st.checkbox("Ferro disponibile?", value=False)
        stock_wood = st.checkbox("Legno disponibile?", value=False)
        stock_screws = st.checkbox("Viteria disponibile?", value=True)
    
    with col_input2:
        st.markdown("#### 2. Logistica")
        log_type = st.radio("Metodo Consegna", ["Corriere", "Nostro Montaggio"], key="log_switch")
        
        costo_corriere = 0.0
        gg_viaggio_corr = 0
        ore_viaggio = 0.0
        ore_montaggio = 0.0
        num_op = 2
        
        if log_type == "Corriere":
            costo_corriere = st.number_input("Costo Spedizione (€)", 0.0, 1000.0, 150.0)
            gg_viaggio_corr = st.number_input("Giorni Viaggio", 1, 10, 2)
        else:
            c_a, c_b = st.columns(2)
            ore_viaggio = c_a.number_input("Ore Viaggio (A/R)", 0.0, 20.0, 2.0, step=0.5)
            ore_montaggio = c_b.number_input("Ore Montaggio", 0.0, 50.0, 4.0, step=0.5)
            num_op = st.slider("Numero Operai", 1, 4, 2)
            
    with col_input3:
        st.markdown("#### 3. Commerciale")
        st.session_state.erp_config['markup_totale'] = st.number_input("Moltiplicatore Ricarico", 1.0, 5.0, st.session_state.erp_config.get('markup_totale', 2.5), step=0.1)
        st.info(f"Prezzi calcolati con ricarico x{st.session_state.erp_config['markup_totale']}")

    # --- CALCOLO LIVE ---
    user_inputs = {
        "start_date": date_start,
        "stock_iron": stock_iron,
        "stock_wood": stock_wood,
        "logistics_type": log_type.lower().replace(" ", "_"),
        "costo_corriere": costo_corriere,
        "gg_viaggio_corriere": gg_viaggio_corr,
        "ore_viaggio": ore_viaggio,
        "ore_montaggio": ore_montaggio,
        "num_operai": num_op,
        "num_cols": num_colonne
    }
    
    totals = calculate_quote(stats_base, user_inputs)
    
    st.divider()
    
    # --- OUTPUT ---
    c_out1, c_out2 = st.columns([2, 1])
    
    with c_out1:
        st.subheader("📊 Preventivo Finale")
        m1, m2, m3 = st.columns(3)
        m1.metric("Imponibile", f"€ {totals['price_ex_vat']:.2f}")
        m2.metric("IVA (22%)", f"€ {totals['vat']:.2f}")
        m3.metric("TOTALE IVATO", f"€ {totals['price_total']:.2f}", delta="Prezzo Cliente")
        
        st.write(f"**Data Consegna Stimata:** {totals['delivery_date']} ({totals['days_total']} gg lavorativi totali)")
        
    with c_out2:
        st.subheader("📑 Documenti")
        
        # PDF TECNICO
        df_wood = pd.DataFrame(wood_list)
        if not df_wood.empty:
            df_wood['Quantità'] = 1
            df_wood_grp = df_wood.groupby(['w', 'd']).count().reset_index()
            df_wood_grp.columns = ['Larghezza', 'Profondità', 'Pezzi']
        else: df_wood_grp = pd.DataFrame()
            
        pdf_tech = generate_pdf_technical(st.session_state['project_name'], [], df_wood_grp, pd.DataFrame(), stats_base, dati_colonne, {"legno": st.session_state['finish_wood']})
        st.download_button("🔧 SCARICA SCHEDA TECNICA (Officina)", pdf_tech, "SchedaProduzione.pdf", "application/pdf", use_container_width=True)
        
        # PDF COMMERCIALE
        proj_data = {
            "project_name": st.session_state['project_name'],
            "num_colonne": num_colonne,
            "finish_wood": st.session_state['finish_wood'],
            "finish_iron": st.session_state['finish_iron']
        }
        client_data = {
            "name": st.session_state['client_name'],
            "address": st.session_state['client_address']
        }
        pdf_comm = generate_pdf_commercial(proj_data, totals, client_data)
        st.download_button("💶 SCARICA PREVENTIVO (Cliente)", pdf_comm, "Preventivo.pdf", "application/pdf", type="primary", use_container_width=True)

    with st.expander("⚙️ Dettagli Avanzati (Costi Interni)"):
        st.json(totals)
        st.write("Configurazione Parametri Attuale:")
        st.json(st.session_state.erp_config)

