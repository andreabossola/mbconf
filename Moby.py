
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
st.set_page_config(layout="wide", page_title="Moby Configurator Full")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        c_logo, c_title = st.columns([1, 4])
        if os.path.exists("logo.png"):
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

VERSION = "v24.1 (RECOVERY FULL)"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- 3. TEMPI & COSTI (CONFIGURAZIONE) ---
DEFAULT_CONFIG = {
    "costo_ferro_kg": 2.0,
    "costo_legno_mq": 30.0, 
    "costo_ora_operaio": 35.0,
    "markup_totale": 2.5,
    "gg_ordine_ferro": 1,
    "gg_arrivo_lastra": 5,
    "gg_taglio_ferro": 1,
    "gg_verniciatura_ferro": 5,
    "gg_verniciatura_legno": 3,
    "gg_attesa_corriere": 2,
    "min_taglio_legno_pezzo": 5.0,
    "min_verniciatura_legno_mq": 20.0,
    "min_assemblaggio_mensola": 5.0,
    "min_preassemblaggio_struttura": 30.0,
    "ore_imballo_base": 1.0,
    "ore_imballo_extra_spedizione": 2.0,
    "costo_imballo_materiale": 20.0,
    "num_operai_trasferta": 2
}

if 'erp_config' not in st.session_state:
    if os.path.exists("erp_default.json"):
        try:
            with open("erp_default.json", "r") as f:
                st.session_state.erp_config = json.load(f)
        except: st.session_state.erp_config = DEFAULT_CONFIG.copy()
    else: st.session_state.erp_config = DEFAULT_CONFIG.copy()

# --- 4. FUNZIONI UTILI ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- 5. MOTORE DXF (RIPRISTINATO COMPLETO) ---
def create_dxf_doc():
    doc = ezdxf.new()
    for name, col in [('TAGLIO',1), ('FORI',5), ('INFO',3)]:
        doc.layers.new(name=name, dxfattribs={'color': col})
    return doc

def draw_part_on_dxf(msp, part, offset_x, offset_y, project_name):
    dim_x, dim_y = part['h'], part['w']
    msp.add_lwpolyline([
        (offset_x, offset_y), (offset_x+dim_x, offset_y), 
        (offset_x+dim_x, offset_y+dim_y), (offset_x, offset_y+dim_y), 
        (offset_x, offset_y)], dxfattribs={'layer': 'TAGLIO'})
    for hx, hy in part['holes']:
        cx, cy = offset_x + hy, offset_y + hx
        msp.add_circle((cx, cy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
    date_str = datetime.now().strftime("%d/%m/%y")
    info_txt = f"{part['lbl']} | {project_name} | {date_str}"
    t = msp.add_text(info_txt, dxfattribs={'layer': 'INFO', 'height': 2.5})
    t.dxf.insert = (offset_x, offset_y + dim_y + 2) 
    return dim_x 

def generate_single_dxf(part, project_name):
    doc = create_dxf_doc()
    msp = doc.modelspace()
    t = msp.add_text(f"PROGETTO: {project_name}", dxfattribs={'layer': 'INFO', 'height': 5.0})
    t.dxf.insert = (0, 50) 
    draw_part_on_dxf(msp, part, 0, 0, project_name)
    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

def generate_full_dxf(parts, project_name):
    doc = create_dxf_doc()
    msp = doc.modelspace()
    date_str = datetime.now().strftime("%d/%m/%Y")
    t = msp.add_text(f"PROGETTO: {project_name} | DATA: {date_str}", dxfattribs={'layer': 'INFO', 'height': 8.0})
    t.dxf.insert = (0, -20) 
    cursor_y, gap = 0, 15 
    for part in parts:
        draw_part_on_dxf(msp, part, 0, cursor_y, project_name)
        cursor_y += part['w'] + gap 
    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

# --- 6. MOTORE 3D (RIPRISTINATO COMPLETO) ---
def add_stl(x,y,z,dx,dy,dz):
    v = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],[x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]]
    idx = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[2,3,7],[2,7,6],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    for t in idx: stl_triangles.append((v[t[0]],v[t[1]],v[t[2]]))

def draw(x,y,z,dx,dy,dz,col,name):
    add_stl(x,y,z,dx,dy,dz)
    xv, yv, zv = [x, x+dx, x+dx, x]*2, [y, y, y+dy, y+dy]*2, [z]*4 + [z+dz]*4
    I,J,K = [0,0,4,4,0,0,2,2,3,3,1,1], [1,2,5,6,1,5,3,7,0,4,2,6], [2,3,6,7,5,4,7,6,4,7,6,5]
    return go.Mesh3d(x=xv, y=yv, z=zv, i=I, j=J, k=K, color=col, opacity=1, flatshading=True, name=name, lighting=dict(ambient=0.6, diffuse=0.8), hoverinfo='name')

def get_bin_stl(tris):
    out = io.BytesIO()
    out.write(b'\0'*80 + struct.pack('<I', len(tris)))
    for p in tris: out.write(struct.pack('<ffffffffffffH', 0,0,0, *p[0], *p[1], *p[2], 0))
    return out.getvalue()

# --- 7. PDF ENGINE (UNIFICATO) ---
class PDFReport(FPDF):
    def __init__(self, project_name, colors, is_commercial=False):
        super().__init__()
        self.project_name = project_name
        self.colors = colors
        self.is_commercial = is_commercial
        
    def header(self):
        if os.path.exists("logo.png"):
            try: self.image("logo.png", 10, 8, 33)
            except: pass
        
        if self.is_commercial:
            self.set_font('Arial', 'B', 16)
            self.cell(0, 10, 'PREVENTIVO', 0, 1, 'R')
            self.set_font('Arial', '', 10)
            self.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
        else:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, 'SCHEDA TECNICA DI PRODUZIONE', 0, 1, 'R')
            self.set_font('Arial', '', 9)
            self.cell(0, 6, f"Progetto: {self.project_name}", 0, 1, 'R')
        
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'{COPYRIGHT} - Pagina ' + str(self.page_no()), 0, 0, 'C')

    def auto_scale(self, needed_width_mm, available_width_mm, max_scale=0.35):
        if needed_width_mm * max_scale > available_width_mm:
            return available_width_mm / needed_width_mm
        return max_scale

def generate_pdf_technical(project_name, parts_list, wood_data, iron_data, stats, cols_data, colors):
    pdf = PDFReport(project_name, colors, is_commercial=False)
    
    # PAG 1: PROSPETTO
    pdf.add_page()
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "PROSPETTO FRONTALE", 0, 1, 'L') 
    
    tot_width_cm = sum([c['w'] + (SPESSORE_FERRO*2) for c in cols_data])
    scale = pdf.auto_scale(tot_width_cm * 10, 180, 0.35)
    
    start_x = 20
    start_y = 60
    current_x = start_x
    pdf.line(10, start_y + 120, 200, start_y + 120) 
    for col in cols_data:
        h, w = col['h'] * scale, col['w'] * scale
        w_ferro_pdf = 0.3
        pdf.set_fill_color(0, 0, 0) 
        pdf.rect(current_x, start_y + (120 - h), w_ferro_pdf, h, 'F') 
        pdf.set_fill_color(180, 180, 180) 
        if col['mh']:
            for z in col['mh']:
                mz = z * scale
                pdf.rect(current_x + w_ferro_pdf, start_y + (120 - mz - (SPESSORE_LEGNO*scale)), w, (SPESSORE_LEGNO*scale), 'F') 
        current_x += w + w_ferro_pdf
        pdf.set_fill_color(0, 0, 0) 
        pdf.rect(current_x, start_y + (120 - h), w_ferro_pdf, h, 'F') 
        current_x += w_ferro_pdf + 0.2 

    # PAG 2: PIANTA (LANDSCAPE)
    pdf.add_page(orientation='L')
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "PIANTA (LANDSCAPE)", 0, 1)
    scale_pianta = pdf.auto_scale(tot_width_cm * 10, 260, 0.65)
    start_x = 20
    start_y = 50
    curr_x_pianta = start_x
    for col in cols_data:
        w_mod = (col['w'] + (SPESSORE_FERRO*2)) * scale_pianta
        d_mod = col['d'] * scale_pianta
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(curr_x_pianta, start_y, w_mod, d_mod, 'D')
        pdf.set_font("Arial", '', 8)
        pdf.set_xy(curr_x_pianta, start_y - 5)
        pdf.cell(w_mod, 5, f"{col['w']:.0f}", 0, 0, 'C')
        pdf.set_xy(curr_x_pianta, start_y + d_mod + 2)
        pdf.cell(w_mod, 5, f"P: {col['d']:.0f}", 0, 0, 'C')
        curr_x_pianta += w_mod

    # PAG 3: LISTE
    pdf.add_page(orientation='P')
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "DISTINTA MATERIALI", 0, 1, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, f"Peso Ferro: {stats['peso_ferro']:.1f} kg", 1)
    pdf.cell(50, 8, f"Peso Legno: {stats['peso_legno']:.1f} kg", 1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "LISTA LEGNO", 0, 1)
    pdf.set_font("Arial", '', 9)
    if not wood_data.empty:
        for index, row in wood_data.iterrows():
            pdf.cell(100, 7, f"N. {row['Pezzi']} Pz - {row['Larghezza']:.0f} x {row['Profondità']:.0f} cm", 1, 1)
    
    return pdf.output(dest='S').encode('latin-1')

def generate_pdf_commercial(project_data, totals, client_data):
    pdf = PDFReport(project_data['project_name'], {}, is_commercial=True)
    pdf.add_page()
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 5, "Spett.le:", 0, 1)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(100, 5, client_data['name'], 0, 1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 5, client_data['address'], 0, 1)
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Oggetto: Fornitura Libreria {project_data['project_name']}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", '', 10)
    desc = f"Libreria composta da {project_data['num_colonne']} moduli.\nFiniture: Ferro {project_data['finish_iron']}, Legno {project_data['finish_wood']}."
    pdf.multi_cell(0, 6, desc)
    pdf.ln(10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(140, 8, "Descrizione", 1, 0, 'L', True)
    pdf.cell(40, 8, "Importo", 1, 1, 'R', True)
    pdf.cell(140, 10, "Struttura su misura", 1, 0)
    pdf.cell(40, 10, f"E {totals['price_ex_vat'] - totals['logistics_price']:.2f}", 1, 1, 'R')
    if totals['logistics_price'] > 0:
        pdf.cell(140, 10, "Trasporto/Logistica", 1, 0)
        pdf.cell(40, 10, f"E {totals['logistics_price']:.2f}", 1, 1, 'R')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(140, 10, "TOTALE IMPONIBILE", 0, 0, 'R')
    pdf.cell(40, 10, f"E {totals['price_ex_vat']:.2f}", 1, 1, 'R')
    pdf.cell(140, 10, "IVA (22%)", 0, 0, 'R')
    pdf.cell(40, 10, f"E {totals['vat']:.2f}", 1, 1, 'R')
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(140, 12, "TOTALE IVATO", 1, 0, 'R', True)
    pdf.cell(40, 12, f"E {totals['price_total']:.2f}", 1, 1, 'R', True)
    return pdf.output(dest='S').encode('latin-1')

# --- 8. LOGICA CALCOLO (PREVENTIVATORE) ---
def calculate_quote(stats, user_inputs):
    cfg = st.session_state.erp_config
    cost_ferro = stats['peso_ferro'] * cfg['costo_ferro_kg']
    cost_legno = stats['mq_legno'] * cfg['costo_legno_mq']
    cost_mat_tot = cost_ferro + cost_legno
    
    # Tempi
    days_iron = 0
    if not user_inputs['stock_iron']: days_iron += cfg['gg_ordine_ferro'] + cfg['gg_arrivo_lastra']
    days_iron += cfg['gg_taglio_ferro'] + cfg['gg_verniciatura_ferro']
    
    mins_cut_wood = stats['num_pezzi_legno'] * cfg['min_taglio_legno_pezzo']
    mins_varnish_wood = stats['mq_legno'] * cfg['min_verniciatura_legno_mq']
    hrs_wood_prod = (mins_cut_wood + mins_varnish_wood) / 60.0
    days_wood_work = (hrs_wood_prod / 8.0) 
    days_wood = days_wood_work + cfg['gg_verniciatura_legno']
    days_production = max(days_iron, days_wood)
    
    mins_pre_shelves = stats['num_pezzi_legno'] * cfg['min_assemblaggio_mensola']
    mins_pre_struct = user_inputs['num_cols'] * cfg['min_preassemblaggio_struttura']
    hrs_pre_assembly = (mins_pre_shelves + mins_pre_struct) / 60.0
    cost_labor_prod = (hrs_wood_prod + hrs_pre_assembly) * cfg['costo_ora_operaio']
    
    log_cost = 0.0
    log_days = 0
    hrs_packing = cfg['ore_imballo_base']
    if user_inputs['logistics_type'] == "corriere":
        hrs_packing += cfg['ore_imballo_extra_spedizione']
        log_cost += user_inputs['costo_corriere']
        log_days += cfg['gg_attesa_corriere'] + user_inputs['gg_viaggio_corriere']
    else:
        total_man_hours_site = (user_inputs['ore_viaggio'] + user_inputs['ore_montaggio']) * user_inputs['num_operai']
        log_cost += total_man_hours_site * cfg['costo_ora_operaio']
        log_days += 1
    
    cost_packing = (hrs_packing * cfg['costo_ora_operaio']) + cfg['costo_imballo_materiale']
    cost_total_production = cost_mat_tot + cost_labor_prod + cost_packing
    
    base_for_markup = cost_total_production + log_cost
    price_final_ex_vat = base_for_markup * cfg['markup_totale']
    vat = price_final_ex_vat * 0.22
    
    final_days = days_production + log_days + 1
    del_date = user_inputs['start_date'] + timedelta(days=int(final_days))
    
    return {
        "price_ex_vat": price_final_ex_vat,
        "vat": vat,
        "price_total": price_final_ex_vat + vat,
        "logistics_price": log_cost * cfg['markup_totale'],
        "days_total": int(final_days),
        "delivery_date": del_date.strftime("%d/%m/%Y")
    }

# --- 9. SIDEBAR & UI ---
load_default_if_exists = lambda: None # Placeholder

with st.sidebar:
    # --- FIX LOGO ---
    if os.path.exists("logo.png"): st.image("logo.png", width=150)
    else: st.title("MOBY ERP")
    st.markdown("---")
    
    if 'project_name' not in st.session_state: st.session_state['project_name'] = "Progetto"
    st.session_state['project_name'] = st.text_input("Nome Progetto", st.session_state['project_name'])
    
    # Cliente & Finiture
    st.markdown("### Dati Cliente & Finiture")
    if 'client_name' not in st.session_state: st.session_state['client_name'] = ""
    st.session_state['client_name'] = st.text_input("Cliente", st.session_state['client_name'])
    if 'client_address' not in st.session_state: st.session_state['client_address'] = ""
    st.session_state['client_address'] = st.text_input("Indirizzo", st.session_state['client_address'])
    
    if 'finish_wood' not in st.session_state: st.session_state['finish_wood'] = "Rovere"
    st.session_state['finish_wood'] = st.text_input("Legno", st.session_state['finish_wood'])
    if 'finish_iron' not in st.session_state: st.session_state['finish_iron'] = "Nero"
    st.session_state['finish_iron'] = st.text_input("Ferro", st.session_state['finish_iron'])

    st.markdown("---")
    num_colonne = st.number_input("N. Moduli", 1, 10, 2)
    
    dati_colonne = []
    wood_list = []
    parts_list = []
    
    for i in range(num_colonne):
        with st.expander(f"Modulo {chr(65+i)}"):
            w = st.number_input("L", 30, 200, 60, key=f"w{i}")
            h = st.number_input("H", 50, 400, 240, key=f"h{i}")
            d = st.number_input("P", 20, 100, 30, key=f"d{i}")
            r = st.number_input("Ripiani", 1, 20, 5, key=f"r{i}")
            step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
            mh = [n*step for n in range(r)]
            
            dati_colonne.append({"w":w, "h":h, "d":d, "r":r, "mh":mh})
            for _ in range(r): wood_list.append({"w":w, "d":d})
            
            # Generazione parti DXF
            holes = []
            for z in mh:
                cy = z + (SPESSORE_LEGNO/2.0)
                holes.append((OFFSET_LATERALI, cy)); holes.append((d/2.0, cy)); holes.append((d-OFFSET_LATERALI, cy))
            parts_list.append({"w":d, "h":h, "lbl":f"M_{chr(65+i)}_SX", "holes":holes})
            parts_list.append({"w":d, "h":h, "lbl":f"M_{chr(65+i)}_DX", "holes":holes})

    # 3D GENERATOR
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
    fig.update_layout(scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), margin=dict(l=0,r=0,t=0,b=0), height=400)

# --- 10. MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["🎥 CONFIGURATORE 3D", "🏭 ESECUTIVI & DXF", "💰 PREVENTIVO"])

with tab1:
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.header("Esecutivi di Produzione")
    
    # Calcolo pesi per distinta
    vol_ferro = sum([p['w']*p['h']*SPESSORE_FERRO for p in parts_list])
    peso_ferro = (vol_ferro * PESO_SPECIFICO_FERRO) / 1000.0
    mq_legno = sum([(x['w']*x['d'])/10000.0 for x in wood_list])
    peso_legno = (mq_legno * SPESSORE_LEGNO * PESO_SPECIFICO_LEGNO * 10) 
    stats_base = {"peso_ferro":peso_ferro, "peso_legno":peso_legno, "mq_legno":mq_legno, "num_pezzi_legno":len(wood_list)}
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.subheader("📦 Download DXF")
        dxf_full = generate_full_dxf(parts_list, st.session_state['project_name'])
        st.download_button("SCARICA DXF COMPLETO", dxf_full, "taglio_completo.dxf", "application/dxf", type="primary", use_container_width=True)
    
    with col_d2:
        st.subheader("📄 Scheda Tecnica")
        df_wood = pd.DataFrame(wood_list)
        if not df_wood.empty:
            df_wood['Qta'] = 1
            df_wood = df_wood.groupby(['w','d']).count().reset_index()
            df_wood.columns = ['Larghezza','Profondità','Pezzi']
        pdf_tech = generate_pdf_technical(st.session_state['project_name'], parts_list, df_wood, pd.DataFrame(), stats_base, dati_colonne, {"legno":st.session_state['finish_wood']})
        st.download_button("SCARICA SCHEDA PDF", pdf_tech, "scheda_tecnica.pdf", "application/pdf", use_container_width=True)

    # Preview DXF
    st.markdown("---")
    st.caption("Anteprima posizionamento DXF")
    fig_dxf = go.Figure()
    cy = 0
    for p in parts_list:
        fig_dxf.add_shape(type="rect", x0=0, y0=cy, x1=p['h'], y1=cy+p['w'], line=dict(color="RoyalBlue"))
        cy += p['w'] + 10
    fig_dxf.update_layout(height=300, xaxis=dict(visible=True, title="Lunghezza"), yaxis=dict(visible=False, scaleanchor="x"))
    st.plotly_chart(fig_dxf, use_container_width=True)

with tab3:
    st.header("Preventivo & Tempi")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### 1. Magazzino")
        date_start = st.date_input("Data Ordine", datetime.now())
        stock_iron = st.checkbox("Ferro OK?", False)
        stock_wood = st.checkbox("Legno OK?", False)
    with c2:
        st.markdown("#### 2. Logistica")
        log_type = st.radio("Metodo", ["Corriere", "Montaggio Nostro"])
        costo_corr = 0.0; gg_corr = 0; ore_v = 0.0; ore_m = 0.0; num_op = 2
        if log_type == "Corriere":
            costo_corr = st.number_input("Costo Sped.", 0.0, 500.0, 150.0)
            gg_corr = st.number_input("GG Viaggio", 1, 10, 2)
        else:
            ore_v = st.number_input("Ore Viaggio", 0.0, 10.0, 2.0)
            ore_m = st.number_input("Ore Montaggio", 0.0, 20.0, 4.0)
            num_op = st.number_input("Operai", 1, 4, 2)
    with c3:
        st.markdown("#### 3. Economico")
        st.session_state.erp_config['markup_totale'] = st.number_input("Ricarico (Markup)", 1.0, 5.0, 2.5)

    # Calcolo
    user_inputs = {
        "start_date": date_start, "stock_iron": stock_iron, "logistics_type": log_type.lower().replace(" ", "_"),
        "costo_corriere": costo_corr, "gg_viaggio_corriere": gg_corr, "ore_viaggio": ore_v, "ore_montaggio": ore_m,
        "num_operai": num_op, "num_cols": num_colonne
    }
    
    totals = calculate_quote(stats_base, user_inputs)
    
    st.divider()
    m1, m2 = st.columns([2,1])
    with m1:
        st.metric("TOTALE PREVENTIVO (IVATO)", f"€ {totals['price_total']:.2f}")
        st.info(f"Consegna stimata: {totals['delivery_date']} ({totals['days_total']} gg lavorativi)")
    with m2:
        proj_data = {"project_name":st.session_state['project_name'], "num_colonne":num_colonne, "finish_iron":st.session_state['finish_iron'], "finish_wood":st.session_state['finish_wood']}
        client_data = {"name":st.session_state['client_name'], "address":st.session_state['client_address']}
        pdf_comm = generate_pdf_commercial(proj_data, totals, client_data)
        st.download_button("💶 SCARICA PREVENTIVO CLIENTE", pdf_comm, "preventivo.pdf", "application/pdf", type="primary", use_container_width=True)
