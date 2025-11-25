
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
st.set_page_config(layout="wide", page_title="Moby Configurator")

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

VERSION = "v24.5 (Labels & Logic Fixed)"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- UTILITY ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- 3. GESTIONE TEMPI & COSTI (AGGIORNATO CON NUOVE VOCI) ---
DEFAULT_COSTS = {
    "costo_ferro_kg": 0.0, "costo_legno_mq": 0.0, "costo_ora_operaio": 0.0, "markup_totale": 2.5,
    
    # Tempi Approvvigionamento
    "gg_ordine_ferro": 1, "gg_arrivo_lastra": 5, 
    "gg_ordine_legno": 2, # NUOVO
    
    # Tempi Verniciatura/Esterni
    "gg_verniciatura_ferro": 5, "gg_verniciatura_legno": 3, "gg_attesa_corriere": 2,
    
    # Lavorazioni (Minuti)
    "min_taglio_legno_pezzo": 0.0, 
    "min_colore_legno_metro": 0.0, 
    "min_preassemblaggio_modulo": 0.0, 
    "min_preassemblaggio_mensola": 0.0,
    "min_assemblaggio_finale_modulo": 30.0, # NUOVO
    
    # Logistica
    "ore_pulizia": 2.0, "ore_imballo_base": 1.0, "ore_imballo_extra": 2.0, 
    "costo_imballo_materiale": 20.0, "ore_prep_spedizione": 2.0
}

def load_costs_config():
    if 'costs_config' not in st.session_state:
        if os.path.exists("tempicosti_default.json"):
            try:
                with open("tempicosti_default.json", "r") as f:
                    loaded = json.load(f)
                    st.session_state.costs_config = DEFAULT_COSTS.copy()
                    st.session_state.costs_config.update(loaded)
            except: st.session_state.costs_config = DEFAULT_COSTS.copy()
        else: st.session_state.costs_config = DEFAULT_COSTS.copy()
load_costs_config()

# --- 4. PDF ENGINE (INVARIATO) ---
class PDFReport(FPDF):
    def __init__(self, project_name, colors):
        super().__init__()
        self.project_name = project_name
        self.colors = colors 
        
    def header(self):
        if os.path.exists("logo.png"):
            try: self.image("logo.png", 10, 8, 33)
            except: pass
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'SCHEDA TECNICA DI PRODUZIONE', 0, 1, 'R')
        self.set_font('Arial', '', 9)
        date_str = datetime.now().strftime('%d/%m/%Y')
        self.cell(0, 6, f"Progetto: {self.project_name} | Data: {date_str}", 0, 1, 'R')
        self.set_font('Arial', 'I', 8)
        self.cell(0, 6, f"Finiture: Legno {self.colors['legno']} - Ferro {self.colors['ferro']}", 0, 1, 'R')
        self.line(10, 30, 200, 30) 
        self.ln(25) 

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'{COPYRIGHT} - Pagina ' + str(self.page_no()), 0, 0, 'C')

    def draw_dimension_line_horz(self, x_start, x_end, y, text):
        self.set_draw_color(0,0,0)
        self.line(x_start, y, x_end, y)
        self.line(x_start, y-1, x_start, y+1)
        self.line(x_end, y-1, x_end, y+1)
        self.set_xy(x_start, y - 4)
        self.set_font("Arial", '', 8)
        self.cell(x_end - x_start, 4, text, 0, 0, 'C')

    def draw_dimension_line_vert(self, x, y_start, y_end, text, align='L'):
        self.line(x, y_start, x, y_end)
        self.line(x-1, y_start, x+1, y_start)
        self.line(x-1, y_end, x+1, y_end)
        mid_y = (y_start + y_end) / 2
        self.set_font("Arial", '', 7)
        if align == 'L':
            self.set_xy(x + 2, mid_y - 2)
            self.cell(10, 4, text, 0, 0, 'L')
        else:
            self.set_xy(x - 12, mid_y - 2)
            self.cell(10, 4, text, 0, 0, 'R')

def generate_pdf_report(project_name, parts_list, wood_data, iron_data, stats, cols_data, colors):
    pdf = PDFReport(project_name, colors)
    # PAG 1: PROSPETTO
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240) 
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "PROSPETTO FRONTALE", 0, 1, 'L', fill=True) 
    pdf.ln(10) 
    start_x = 20
    start_y = pdf.get_y() + 20 
    scale = 0.35 
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
    # PAG 2: LOGISTICA
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "RIEPILOGO MATERIALI", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", size=10)
    pdf.cell(45, 8, f"Peso Ferro: {stats['peso_ferro']:.1f} kg", 1)
    pdf.cell(45, 8, f"Peso Legno: {stats['peso_legno']:.1f} kg", 1)
    pdf.cell(45, 8, f"Totale: {stats['peso_tot']:.1f} kg", 1)
    pdf.cell(55, 8, f"Viteria: {stats['viti']} pz", 1, 1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "DISTINTA LEGNO", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 9)
    if not wood_data.empty:
        for index, row in wood_data.iterrows():
            pdf.cell(40, 8, f"{row['Larghezza']:.0f} x {row['Profondità']:.0f}", 1)
            pdf.cell(40, 8, f"{row['Pezzi']}", 1)
            pdf.cell(40, 8, f"{row['Metri Totali']:.1f} m", 1, 1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "DISTINTA FERRO", 0, 1, 'L', fill=True)
    pdf.ln(2)
    if not iron_data.empty:
        for index, row in iron_data.iterrows():
            pdf.cell(40, 8, f"{row['Altezza']:.0f} x {row['Profondità']:.0f}", 1)
            pdf.cell(40, 8, f"{row['Pezzi']}", 1)
            pdf.ln()
    # PAG 3: PIANTA
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "PIANTA (VISTA DALL'ALTO)", 0, 1, 'L', fill=True)
    pdf.ln(20)
    tot_len_cm = sum([c['w'] + (SPESSORE_FERRO*2) for c in cols_data])
    scale_pianta = 0.65 
    start_x = 70 
    start_y = pdf.get_y() + 20 
    current_y = start_y
    pdf.draw_dimension_line_vert(start_x - 15, start_y, start_y + (tot_len_cm * scale_pianta), f"TOT: {tot_len_cm:.1f}", 'R')
    for col in cols_data:
        w_mod_scaled = (col['w'] + (SPESSORE_FERRO*2)) * scale_pianta 
        d_mod_scaled = col['d'] * scale_pianta 
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        pdf.rect(start_x, current_y, d_mod_scaled, w_mod_scaled)
        pdf.set_xy(start_x, current_y - 5)
        pdf.set_font("Arial", '', 8)
        pdf.cell(d_mod_scaled, 5, f"P: {col['d']:.0f}", 0, 0, 'C')
        pdf.draw_dimension_line_vert(start_x + d_mod_scaled + 5, current_y, current_y + w_mod_scaled, f"{col['w']:.0f}", 'L')
        current_y += w_mod_scaled 
    # PAG 4+: DETTAGLI
    scale_det = 0.45 
    for col in cols_data:
        pdf.add_page()
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, f"DETTAGLIO MODULO {col['letter']}", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 8, f"Dimensioni: {col['w']} (L) x {col['h']} (H) x {col['d']} (P) cm  |  {col['r']} Mensole", 0, 1, 'L')
        pdf.ln(5)
        h_front = col['h'] * scale_det
        base_y = (297 / 2) + (h_front / 2) + 20 
        center_x = 105 
        w_front = col['w'] * scale_det
        x_front = center_x - w_front - 20 
        w_ferro_det = 0.5 
        z_vals = [] 
        if col['mh']:
            for z in col['mh']:
                z_vals.append(z + (SPESSORE_LEGNO/2.0))
                mz = z * scale_det
                pdf.set_fill_color(180,180,180)
                pdf.rect(x_front + w_ferro_det, base_y - mz - (SPESSORE_LEGNO*scale_det), w_front, (SPESSORE_LEGNO*scale_det), 'F')
        pdf.set_fill_color(0,0,0)
        pdf.rect(x_front, base_y - h_front, w_ferro_det, h_front, 'F')
        pdf.rect(x_front + w_front + w_ferro_det, base_y - h_front, w_ferro_det, h_front, 'F')
        pdf.set_xy(x_front, base_y - h_front - 5)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_front + (w_ferro_det*2), 5, "VISTA FRONTALE", 0, 0, 'C')
        pdf.draw_dimension_line_horz(x_front, x_front + w_front + (w_ferro_det*2), base_y + 5, f"L: {col['w']:.0f}")
        line_x = center_x
        line_top = base_y - h_front
        line_bot = base_y
        pdf.line(line_x, line_top, line_x, line_bot)
        pdf.draw_dimension_line_vert(line_x, line_top, line_bot, f"H Tot: {col['h']:.1f}", 'R')
        z_vals_sorted = sorted(z_vals)
        points = [0.0] + z_vals_sorted + [col['h']]
        for i in range(len(points)-1):
            val_curr = points[i]
            val_next = points[i+1]
            y_curr = base_y - (val_curr * scale_det)
            y_next = base_y - (val_next * scale_det)
            pdf.line(line_x - 2, y_curr, line_x + 2, y_curr)
            pdf.line(line_x - 2, y_next, line_x + 2, y_next)
            dist = val_next - val_curr
            if dist > 3: 
                mid_y_quota = (y_curr + y_next) / 2
                pdf.set_xy(line_x + 3, mid_y_quota - 2)
                pdf.cell(10, 4, f"{dist:.1f}", 0, 0, 'L')
        x_side = center_x + 40
        w_side = col['d'] * scale_det
        h_side = col['h'] * scale_det
        pdf.set_fill_color(255,255,255)
        pdf.set_draw_color(0,0,0)
        pdf.rect(x_side, base_y - h_side, w_side, h_side)
        pdf.set_fill_color(0,0,0)
        holes_x = [OFFSET_LATERALI, col['d']/2, col['d']-OFFSET_LATERALI]
        for z in z_vals:
            y_hole = base_y - (z * scale_det)
            for hx in holes_x:
                x_hole = x_side + (hx * scale_det)
                pdf.ellipse(x_hole-0.7, y_hole-0.7, 1.4, 1.4, 'F')
        pdf.set_xy(x_side, base_y - h_side - 5)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_side, 5, "VISTA LATERALE", 0, 0, 'C')
        pdf.draw_dimension_line_horz(x_side, x_side + w_side, base_y + 5, f"P: {col['d']:.0f}")
    # PAG ESECUTIVI
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "ESECUTIVI DI TAGLIO (FERRO)", 0, 1, 'L', fill=True)
    pdf.ln(10)
    scale_cut = 0.5 
    cursor_y = pdf.get_y() + 10
    for part in parts_list:
        req_h = (part['w'] * scale_cut) + 25
        if cursor_y + req_h > 270:
            pdf.add_page()
            cursor_y = 40 
        start_x = 20
        pdf.set_fill_color(255, 255, 255) 
        pdf.rect(start_x, cursor_y, part['h']*scale_cut, part['w']*scale_cut)
        pdf.set_fill_color(0, 0, 0) 
        for hx, hy in part['holes']:
            cx = start_x + (hy * scale_cut)
            cy = cursor_y + (hx * scale_cut)
            pdf.ellipse(cx-0.5, cy-0.5, 1.0, 1.0, 'F')
        pdf.set_xy(start_x, cursor_y - 6)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 5, f"{part['lbl']} ({part['h']}x{part['w']} cm)", 0, 0)
        cursor_y += req_h 
    return pdf.output(dest='S').encode('latin-1')

# --- 4.1 NUOVA FUNZIONE PDF COMMERCIALE (Separata) ---
class CommercialPDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"):
            try: self.image("logo.png", 10, 8, 40)
            except: pass
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'PREVENTIVO', 0, 1, 'R')
        self.set_font('Arial', '', 10)
        self.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
        self.ln(20)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'{COPYRIGHT} - Pagina ' + str(self.page_no()), 0, 0, 'C')

def generate_commercial_pdf(project_data, totals, client_data):
    pdf = CommercialPDF()
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
    desc = f"Libreria composta da {project_data['num_colonne']} moduli.\nFiniture: {project_data['finish_wood']} / {project_data['finish_iron']}."
    pdf.multi_cell(0, 6, desc)
    pdf.ln(10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(140, 8, "Descrizione", 1, 0, 'L', True)
    pdf.cell(40, 8, "Importo", 1, 1, 'R', True)
    pdf.cell(140, 10, "Struttura su misura (Materiali e Lavorazione)", 1, 0)
    pdf.cell(40, 10, f"E {totals['price_ex_vat'] - totals['logistics_price']:.2f}", 1, 1, 'R')
    if totals['logistics_price'] > 0:
        desc_log = "Spedizione Corriere" if totals['logistics_type'] == "corriere" else "Trasporto e Montaggio in loco"
        pdf.cell(140, 10, desc_log, 1, 0)
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
    pdf.set_text_color(0, 0, 0)
    pdf.ln(15)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"Data Consegna Stimata: {totals['delivery_date']}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. LOGICA PREVENTIVATORE (FIXED & EXPANDED) ---
def calculate_quote_logic(stats, user_inputs):
    cfg = st.session_state.costs_config
    
    # 1. Materiali
    cost_ferro = stats['peso_ferro'] * cfg.get('costo_ferro_kg', 0)
    mq_legno = (stats['peso_legno'] / PESO_SPECIFICO_LEGNO / SPESSORE_LEGNO / 10.0) 
    cost_legno = mq_legno * cfg.get('costo_legno_mq', 0)
    cost_mat_tot = cost_ferro + cost_legno
    
    # 2. Tempi Paralleli
    # Ferro
    days_iron = 0
    if not user_inputs['stock_iron']: days_iron += cfg.get('gg_ordine_ferro', 1) + cfg.get('gg_arrivo_lastra', 5)
    days_iron += cfg.get('gg_verniciatura_ferro', 5)
    
    # Legno
    days_wood_supply = 0
    if not user_inputs['stock_wood']: days_wood_supply = cfg.get('gg_ordine_legno', 2)
    
    mins_legno_lavorazione = (stats['viti']/6 * cfg.get('min_taglio_legno_pezzo', 0)) + (mq_legno * cfg.get('min_colore_legno_metro', 0))
    hrs_legno = mins_legno_lavorazione / 60.0
    days_wood_work = hrs_legno / 8.0
    days_wood = days_wood_supply + days_wood_work + cfg.get('gg_verniciatura_legno', 3)
    
    days_production = max(days_iron, days_wood)
    
    # 3. Manodopera Produzione
    mins_pre = (user_inputs['num_cols'] * cfg.get('min_preassemblaggio_modulo', 0)) + (stats['viti']/6 * cfg.get('min_preassemblaggio_mensola', 0))
    # Aggiunta Assemblaggio Finale
    mins_final = user_inputs['num_cols'] * cfg.get('min_assemblaggio_finale_modulo', 0)
    
    hrs_prod_tot = hrs_legno + ((mins_pre + mins_final) / 60.0)
    cost_labor_prod = hrs_prod_tot * cfg.get('costo_ora_operaio', 0)
    
    # 4. Logistica
    log_cost = 0.0; log_days = 0; hrs_packing = cfg.get('ore_imballo_base', 1.0)
    if user_inputs['logistics_type'] == "corriere":
        hrs_packing += cfg.get('ore_imballo_extra', 2.0)
        log_cost += user_inputs['costo_corriere']
        log_days += cfg.get('gg_attesa_corriere', 2) + user_inputs['gg_viaggio_corriere']
    else:
        tot_man_hrs = (user_inputs['ore_viaggio'] + user_inputs['ore_montaggio']) * user_inputs['num_operai']
        log_cost += tot_man_hrs * cfg.get('costo_ora_operaio', 0)
        log_days += 1
    cost_packing = (hrs_packing * cfg.get('costo_ora_operaio', 0)) + cfg.get('costo_imballo_materiale', 0)
    
    # 5. Totali
    cost_base = cost_mat_tot + cost_labor_prod + cost_packing
    base_markup = cost_base + log_cost
    price_ex_vat = base_markup * cfg.get('markup_totale', 2.5)
    vat = price_ex_vat * 0.22
    del_date = user_inputs['start_date'] + timedelta(days=int(days_production + log_days + 1))
    
    return {
        "price_ex_vat": price_ex_vat, "vat": vat, "price_total": price_ex_vat + vat,
        "logistics_price": log_cost * cfg.get('markup_totale', 2.5), 
        "logistics_type": user_inputs['logistics_type'], "delivery_date": del_date.strftime("%d/%m/%Y"),
        "days_total": int(days_production + log_days + 1)
    }

# --- 6. DXF & STL ENGINE (INVARIATO) ---
def create_dxf_doc():
    doc = ezdxf.new()
    for name, col in [('TAGLIO',1), ('FORI',5), ('INFO',3)]: doc.layers.new(name=name, dxfattribs={'color': col})
    return doc
def draw_part_on_dxf(msp, part, offset_x, offset_y, project_name):
    dim_x, dim_y = part['h'], part['w']
    msp.add_lwpolyline([(offset_x, offset_y), (offset_x+dim_x, offset_y), (offset_x+dim_x, offset_y+dim_y), (offset_x, offset_y+dim_y), (offset_x, offset_y)], dxfattribs={'layer': 'TAGLIO'})
    for hx, hy in part['holes']: msp.add_circle((offset_x + hy, offset_y + hx), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
    t = msp.add_text(f"{part['lbl']} | {project_name}", dxfattribs={'layer': 'INFO', 'height': 2.5}); t.dxf.insert = (offset_x, offset_y + dim_y + 2) 
    return dim_x 
def generate_single_dxf(part, project_name):
    doc = create_dxf_doc(); msp = doc.modelspace(); draw_part_on_dxf(msp, part, 0, 0, project_name)
    out = io.StringIO(); doc.write(out); return out.getvalue()
def generate_full_dxf(parts, project_name):
    doc = create_dxf_doc(); msp = doc.modelspace(); cursor_y = 0
    for part in parts: draw_part_on_dxf(msp, part, 0, cursor_y, project_name); cursor_y += part['w'] + 15
    out = io.StringIO(); doc.write(out); return out.getvalue()
def add_stl(x,y,z,dx,dy,dz):
    v = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],[x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]]
    idx = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[2,3,7],[2,7,6],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    for t in idx: stl_triangles.append((v[t[0]],v[t[1]],v[t[2]]))
def draw(x,y,z,dx,dy,dz,col,name):
    add_stl(x,y,z,dx,dy,dz); xv, yv, zv = [x, x+dx, x+dx, x]*2, [y, y, y+dy, y+dy]*2, [z]*4 + [z+dz]*4
    I,J,K = [0,0,4,4,0,0,2,2,3,3,1,1], [1,2,5,6,1,5,3,7,0,4,2,6], [2,3,6,7,5,4,7,6,4,7,6,5]
    return go.Mesh3d(x=xv, y=yv, z=zv, i=I, j=J, k=K, color=col, opacity=1, flatshading=True, name=name)
def get_bin_stl(tris):
    out = io.BytesIO(); out.write(b'\0'*80 + struct.pack('<I', len(tris))); 
    for p in tris: out.write(struct.pack('<ffffffffffffH', 0,0,0, *p[0], *p[1], *p[2], 0))
    return out.getvalue()
def load_default_if_exists():
    if 'data_loaded' in st.session_state: return
    if os.path.exists("default.json"): 
        try: apply_json_data(json.load(open("default.json")))
        except: pass
    st.session_state.data_loaded = True
def apply_json_data(data):
    st.session_state['project_name'] = data.get('project_name', 'Progetto')
    st.session_state['num_colonne'] = data.get('num_colonne', 2)
    st.session_state['client_name'] = data.get('client_name', '')
    st.session_state['client_address'] = data.get('client_address', '')
    st.session_state['finish_wood'] = data.get('finish_wood', 'Rovere Naturale')
    st.session_state['finish_iron'] = data.get('finish_iron', 'Nero Opaco')
    for i, col in enumerate(data.get('cols', [])):
        st.session_state[f"w_{i}"] = col.get('w', 60); st.session_state[f"h_{i}"] = col.get('h', 200)
        st.session_state[f"d_{i}"] = col.get('d', 30); st.session_state[f"r_{i}"] = col.get('r', 4)
        st.session_state[f"man_{i}"] = col.get('manual', False)
        if 'man_heights' in col: 
            for j, val in enumerate(col['man_heights']): st.session_state[f"h_shelf_{i}_{j}"] = val
def load_user_file(f):
    if f is None or ('last_loaded_file' in st.session_state and st.session_state.last_loaded_file == f.name): return
    try: apply_json_data(json.load(f)); st.session_state.last_loaded_file = f.name; st.success("Caricato!")
    except Exception as e: st.error(f"Errore: {e}")

# --- 7. SIDEBAR (INVARIATO) ---
load_default_if_exists()
with st.sidebar:
    try: st.image("logo.png", width=200) 
    except: st.markdown("## MOBY")
    st.markdown("### MOBY CONFIGURATOR")
    st.caption(COPYRIGHT)
    st.divider()
    if 'project_name' not in st.session_state: st.session_state['project_name'] = "Progetto"
    st.text_input("Nome Progetto", key='project_name_input', value=st.session_state['project_name'])
    st.session_state['project_name'] = clean_filename(st.session_state['project_name_input'])
    f = st.file_uploader("Carica JSON", type=["json"]); 
    if f: load_user_file(f)
    st.divider()
    st.markdown("#### Dati Cliente")
    if 'client_name' not in st.session_state: st.session_state['client_name'] = ""
    st.text_input("Ragione Sociale / Nome", key='client_name')
    if 'client_address' not in st.session_state: st.session_state['client_address'] = ""
    st.text_input("Indirizzo / Città", key='client_address')
    st.markdown("#### Finiture")
    if 'finish_wood' not in st.session_state: st.session_state['finish_wood'] = "Rovere Naturale"
    st.text_input("Finitura Legno", key='finish_wood')
    if 'finish_iron' not in st.session_state: st.session_state['finish_iron'] = "Nero Opaco"
    st.text_input("Finitura Ferro", key='finish_iron')
    st.divider()
    st.header("📐 Moduli")
    if 'num_colonne' not in st.session_state: st.session_state['num_colonne'] = 2
    num_colonne = st.number_input("Quantità Moduli", min_value=1, max_value=10, key="num_colonne")
    dati_colonne = []; parts_list = []; wood_list = []; iron_stats_list = []
    for i in range(num_colonne):
        module_letter = chr(65 + i)
        with st.expander(f"Modulo {module_letter}", expanded=False):
            c1, c2 = st.columns(2)
            def_w = st.session_state.get(f"w_{i}", 60); def_h = st.session_state.get(f"h_{i}", 200)
            def_d = st.session_state.get(f"d_{i}", 30); def_r = st.session_state.get(f"r_{i}", 4)
            def_man = st.session_state.get(f"man_{i}", False)
            w = c1.number_input("L", 30, 200, value=def_w, key=f"w_{i}"); d = c2.number_input("P", 20, 100, value=def_d, key=f"d_{i}")
            c3, c4 = st.columns(2)
            h = c3.number_input("H", 50, 400, value=def_h, key=f"h_{i}"); r = c4.number_input("Alt. Mensole", 1, 20, value=def_r, key=f"r_{i}")
            is_manual = st.checkbox("Alt. Mensole", value=def_man, key=f"man_{i}")
            mh = []; z_shelves = []
            if is_manual:
                step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
                for k in range(r):
                    def_shelf = int(k*step); 
                    if k == r-1 and r > 1: def_shelf = int(h - SPESSORE_LEGNO)
                    saved = st.session_state.get(f"h_shelf_{i}_{k}", def_shelf)
                    val = st.number_input(f"M {k+1}", value=saved, key=f"h_shelf_{i}_{k}"); mh.append(val)
                z_shelves = [float(x) for x in mh]
            else:
                if r == 1: z_shelves = [0.0]
                else: step = (h - SPESSORE_LEGNO)/(r-1); z_shelves = [n*step for n in range(r)]
            dati_colonne.append({"w":w, "h":h, "d":d, "r":r, "man":is_manual, "mh":z_shelves, "letter": module_letter})
            holes_coords = []
            for z in z_shelves:
                cy = z + (SPESSORE_LEGNO / 2.0); holes_coords.append((OFFSET_LATERALI, cy)); holes_coords.append((d / 2.0, cy)); holes_coords.append((d - OFFSET_LATERALI, cy)) 
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_SX", "holes": holes_coords})
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_DX", "holes": holes_coords})
            iron_stats_list.append({"Altezza": h, "Profondità": d}); iron_stats_list.append({"Altezza": h, "Profondità": d})
            for _ in range(r): wood_list.append({"w": w, "d": d})
    
    # 3D
    fig = go.Figure(); camera = dict(eye=dict(x=0.0, y=-2.5, z=0.1)); cx = 0 
    for dc in dati_colonne:
        lbl = f"Mod {dc['letter']}"; fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', f"Ferro SX {lbl}")); cx += SPESSORE_FERRO
        for idx, z in enumerate(dc["mh"]): fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, '#D2B48C', f"Piano {idx+1} {lbl}"))
        cx += dc["w"]; fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', f"Ferro DX {lbl}")); cx += SPESSORE_FERRO
    
    # EXPORT FOOTER
    st.divider(); st.header("SALVA / ESPORTA"); ts = get_timestamp_string(); prj = st.session_state['project_name']; fname_json = f"{prj}_{ts}.json"; fname_stl = f"{prj}_{ts}.stl"
    cols_to_save = []
    for dc in dati_colonne: cols_to_save.append({"w": dc['w'], "h": dc['h'], "d": dc['d'], "r": dc['r'], "manual": dc['man'], "man_heights": dc['mh']})
    proj_data = {"project_name": prj, "num_colonne":st.session_state.num_colonne, "cols":cols_to_save, "client_name": st.session_state['client_name'], "client_address": st.session_state['client_address'], "finish_wood": st.session_state['finish_wood'], "finish_iron": st.session_state['finish_iron']}
    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj_data), fname_json, "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), fname_stl, "application/octet-stream")
    st.divider(); st.caption(VERSION)

# --- 8. TABS MAIN ---
tab1, tab2, tab3 = st.tabs(["🎥 3D Config", "🏭 ESECUTIVI PRODUZIONE", "💰 PREVENTIVATORE"])

with tab1:
    fig.update_layout(scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(title="H"), aspectmode='data', bgcolor="white"), scene_camera=camera, uirevision='constant', margin=dict(t=0,b=0,l=0,r=0), height=600)
    st.plotly_chart(fig, width="stretch")

with tab2:
    st.markdown(f"### Distinta Materiali - {prj}")
    vol_ferro = sum([p['w'] * p['h'] * SPESSORE_FERRO for p in parts_list]); peso_ferro = (vol_ferro * PESO_SPECIFICO_FERRO) / 1000.0
    vol_legno = sum([w['w'] * w['d'] * SPESSORE_LEGNO for w in wood_list]); peso_legno = (vol_legno * PESO_SPECIFICO_LEGNO) / 1000.0
    num_viti = len(wood_list) * 6; stats = {"peso_ferro": peso_ferro, "peso_legno": peso_legno, "peso_tot": peso_ferro + peso_legno, "viti": num_viti}
    
    df_legno = pd.DataFrame(wood_list); distinta_legno_pdf = pd.DataFrame()
    if not df_legno.empty:
        df_legno['Quantità'] = 1; distinta_legno_pdf = df_legno.groupby(['w', 'd']).count().reset_index()
        distinta_legno_pdf['Metri Totali'] = (distinta_legno_pdf['w'] * distinta_legno_pdf['Quantità']) / 100.0; distinta_legno_pdf.columns = ['Larghezza', 'Profondità', 'Pezzi', 'Metri Totali']
    df_ferro = pd.DataFrame(iron_stats_list); distinta_ferro_pdf = pd.DataFrame()
    if not df_ferro.empty: df_ferro['Quantità'] = 1; distinta_ferro_pdf = df_ferro.groupby(['Altezza', 'Profondità']).count().reset_index(); distinta_ferro_pdf.columns = ['Altezza', 'Profondità', 'Pezzi']
    
    c_info1, c_info2, c_info3, c_info4 = st.columns(4)
    c_info1.metric("Peso Totale", f"{stats['peso_tot']:.1f} kg"); c_info2.metric("Peso Ferro", f"{stats['peso_ferro']:.1f} kg")
    c_info3.metric("Peso Legno", f"{stats['peso_legno']:.1f} kg"); c_info4.metric("Viteria", f"{num_viti} pz")
    
    colors_data = {"legno": st.session_state['finish_wood'], "ferro": st.session_state['finish_iron']}
    fname_pdf = f"{prj}_{ts}_SchedaTecnica.pdf"
    if st.button("📄 GENERA SCHEDA TECNICA PDF", type="primary", use_container_width=True):
        pdf_bytes = generate_pdf_report(prj, parts_list, distinta_legno_pdf, distinta_ferro_pdf, stats, dati_colonne, colors_data)
        st.download_button("📥 SCARICA PDF", pdf_bytes, fname_pdf, "application/pdf")
    
    st.divider(); c_sx, c_dx = st.columns(2)
    with c_sx: st.subheader("🌲 Distinta Legno"); st.dataframe(distinta_legno_pdf, hide_index=True, use_container_width=True)
    with c_dx: st.subheader("⛓️ Distinta Ferro"); st.dataframe(distinta_ferro_pdf, hide_index=True, use_container_width=True)
    st.divider(); st.subheader("📦 Esecutivi Taglio (Anteprima Completa)")
    fname_dxf_full = f"{prj}_{ts}_Tutto.dxf"; dxf_full = generate_full_dxf(parts_list, prj)
    st.download_button("📦 SCARICA DXF UNICO", dxf_full, fname_dxf_full, "application/dxf", type="primary", use_container_width=True)
    st.write("##")
    
    # FIX SCALA PREVIEW DXF
    fig_all = go.Figure(); cursor_y_plot = 0; gap_plot = 30 
    for idx, part in enumerate(parts_list):
        dim_x, dim_y = part['h'], part['w']; fig_all.add_shape(type="rect", x0=0, y0=cursor_y_plot, x1=dim_x, y1=cursor_y_plot+dim_y, line=dict(color="#E0E0E0", width=2))
        x_holes = [hy for hx, hy in part['holes']]; y_holes = [cursor_y_plot + hx for hx, hy in part['holes']] 
        fig_all.add_trace(go.Scatter(x=x_holes, y=y_holes, mode='markers', marker=dict(color='#00FFFF', size=6), hoverinfo='skip'))
        fig_all.add_annotation(x=dim_x/2, y=cursor_y_plot + dim_y/2, text=part['lbl'], showarrow=False, font=dict(size=14, color="white"))
        cursor_y_plot += dim_y + gap_plot
    fig_all.update_layout(xaxis=dict(title="Lunghezza (cm)", showgrid=True), yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1), height=600, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig_all, width="stretch")
    
    with st.expander("📂 Scarica DXF Pezzi Singoli"):
        for idx, part in enumerate(parts_list):
            c_name, c_down = st.columns([4, 1]); c_name.write(f"**{part['lbl']}** ({part['h']}x{part['w']} cm)")
            c_down.download_button("⬇️ DXF", generate_single_dxf(part, prj), f"{part['lbl']}.dxf", "application/dxf", key=f"dxf_{idx}")

with tab3:
    st.header("💰 Preventivatore & Tempi")
    st.info("Compila i parametri per il calcolo. I risultati appaiono in fondo.")
    
    # 1. SETUP LOGISTICA E STOCK (AGGIORNATO)
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        st.subheader("1. Data & Magazzino")
        date_start = st.date_input("Data Conferma Ordine", datetime.now())
        stock_iron = st.checkbox("Ferro disponibile in magazzino?", value=False)
        stock_wood = st.checkbox("Legno disponibile in magazzino?", value=False) # NUOVO
        
    with c_set2:
        st.subheader("2. Spedizione / Montaggio")
        log_type = st.radio("Tipo Consegna", ["Corriere", "Nostro Montaggio"])
        costo_corriere = 0.0; gg_viaggio_corr = 0; ore_viaggio = 0.0; ore_montaggio = 0.0; num_op = 2
        if log_type == "Corriere":
            costo_corriere = st.number_input("Costo Spedizione (€)", 0.0, 2000.0, 150.0)
            gg_viaggio_corr = st.number_input("Giorni Viaggio Corriere", 1, 15, 2)
        else:
            ore_viaggio = st.number_input("Ore Viaggio (A/R)", 0.0, 20.0, 2.0)
            ore_montaggio = st.number_input("Ore Montaggio in Loco", 0.0, 50.0, 4.0)
            num_op = st.number_input("Numero Operai", 1, 5, 2)

    st.write("---")
    
    # 2. INPUT COSTI (AGGIORNATI CON ETICHETTE CHIARE)
    with st.expander("🛠️ Costi Materiali e Ricarico", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        st.session_state.costs_config['costo_ferro_kg'] = c1.number_input("Ferro (€/kg)", value=st.session_state.costs_config.get('costo_ferro_kg', 0.0))
        st.session_state.costs_config['costo_legno_mq'] = c2.number_input("Legno (€/mq)", value=st.session_state.costs_config.get('costo_legno_mq', 0.0))
        st.session_state.costs_config['costo_ora_operaio'] = c3.number_input("Operaio (€/h)", value=st.session_state.costs_config.get('costo_ora_operaio', 0.0))
        st.session_state.costs_config['markup_totale'] = c4.number_input("Markup Vendita (X)", value=st.session_state.costs_config.get('markup_totale', 2.5), step=0.1)

    with st.expander("⏱️ Tempi Approvvigionamento (Giorni)", expanded=False):
        c1, c2, c3 = st.columns(3)
        st.session_state.costs_config['gg_ordine_ferro'] = c1.number_input("Ordine Ferro", value=st.session_state.costs_config.get('gg_ordine_ferro', 1))
        st.session_state.costs_config['gg_arrivo_lastra'] = c2.number_input("Arrivo Lastra", value=st.session_state.costs_config.get('gg_arrivo_lastra', 5))
        st.session_state.costs_config['gg_ordine_legno'] = c3.number_input("Ordine Legno", value=st.session_state.costs_config.get('gg_ordine_legno', 2)) # NUOVO

    with st.expander("🔨 Tempi Lavorazione (Minuti)", expanded=False):
        c1, c2 = st.columns(2)
        st.session_state.costs_config['min_taglio_legno_pezzo'] = c1.number_input("Taglio Legno (min/pezzo)", value=st.session_state.costs_config.get('min_taglio_legno_pezzo', 5.0))
        st.session_state.costs_config['min_colore_legno_metro'] = c2.number_input("Colore Legno (min/metro)", value=st.session_state.costs_config.get('min_colore_legno_metro', 15.0))
        
        c3, c4 = st.columns(2)
        st.session_state.costs_config['min_preassemblaggio_modulo'] = c3.number_input("Pre-ass Modulo (min/modulo)", value=st.session_state.costs_config.get('min_preassemblaggio_modulo', 30.0))
        st.session_state.costs_config['min_preassemblaggio_mensola'] = c4.number_input("Pre-ass Mensola (min/pezzo)", value=st.session_state.costs_config.get('min_preassemblaggio_mensola', 5.0))
        
        # NUOVO CAMPO ASSEMBLAGGIO FINALE
        st.session_state.costs_config['min_assemblaggio_finale_modulo'] = st.number_input("Assemblaggio Finale (min/modulo)", value=st.session_state.costs_config.get('min_assemblaggio_finale_modulo', 30.0))
    
    # 3. CALCOLO E OUTPUT
    vol_ferro_c = sum([p['w']*p['h']*SPESSORE_FERRO for p in parts_list]); peso_ferro_c = (vol_ferro_c * PESO_SPECIFICO_FERRO) / 1000.0
    vol_legno_c = sum([w['w']*w['d']*SPESSORE_LEGNO for w in wood_list]); peso_legno_c = (vol_legno_c * PESO_SPECIFICO_LEGNO) / 1000.0
    num_viti_c = len(wood_list) * 6
    stats_calc = {"peso_ferro": peso_ferro_c, "peso_legno": peso_legno_c, "viti": num_viti_c}
    
    user_inputs = {
        "start_date": date_start, 
        "stock_iron": stock_iron, 
        "stock_wood": stock_wood, # NUOVO
        "logistics_type": log_type.lower().replace(" ", "_"),
        "costo_corriere": costo_corriere, "gg_viaggio_corriere": gg_viaggio_corr,
        "ore_viaggio": ore_viaggio, "ore_montaggio": ore_montaggio, "num_operai": num_op, "num_cols": num_colonne
    }
    
    totals = calculate_quote_logic(stats_calc, user_inputs)
    
    st.divider()
    m1, m2 = st.columns(2)
    m1.metric("PREZZO TOTALE IVATO", f"€ {totals['price_total']:.2f}", f"Imponibile: € {totals['price_ex_vat']:.2f}")
    m2.success(f"Consegna Stimata: {totals['delivery_date']} ({totals['days_total']} gg lavorativi)")
    
    if st.button("📄 GENERA PREVENTIVO CLIENTE (PDF)", type="primary"):
        pdf_comm = generate_commercial_pdf(proj_data, totals, {"name": st.session_state['client_name'], "address": st.session_state['client_address']})
        st.download_button("SCARICA PREVENTIVO", pdf_comm, f"Preventivo_{st.session_state['client_name']}.pdf", "application/pdf")
        
    st.markdown("---")
    st.download_button("💾 Salva Configurazione Prezzi", json.dumps(st.session_state.costs_config), "tempicosti_default.json", "application/json")
