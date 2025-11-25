
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 
import pandas as pd
import os
from datetime import datetime
from fpdf import FPDF

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby v1.9.1 Detail Fix")

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

# --- 2. COSTANTI ---
SPESSORE_LEGNO = 4.0 
SPESSORE_FERRO = 0.3 
DIAMETRO_FORO = 0.6 
OFFSET_LATERALI = 3.0
PESO_SPECIFICO_FERRO = 7.85 
PESO_SPECIFICO_LEGNO = 0.70 

VERSION = "v1.9.1 Detail Zoom"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- UTILITY ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- 3. PDF GENERATOR ENGINE ---
class PDFReport(FPDF):
    def header(self):
        if os.path.exists("logo.png"):
            try: self.image("logo.png", 10, 8, 33)
            except: pass
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'SCHEDA TECNICA DI PRODUZIONE', 0, 1, 'R')
        self.ln(20)

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

def generate_pdf_report(project_name, parts_list, wood_data, iron_data, stats, cols_data):
    pdf = PDFReport()
    
    # PAG 1
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Progetto: {project_name}", ln=True)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
    pdf.ln(5)
    
    pdf.set_fill_color(240, 240, 240) 
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "PROSPETTO FRONTALE (MUTO)", 0, 1, 'L', fill=True) 
    pdf.ln(10)
    
    start_x = 20
    start_y = pdf.get_y() + 10
    scale = 0.35 
    current_x = start_x
    
    pdf.line(10, start_y + 120, 200, start_y + 120) 
    
    for col in cols_data:
        h, w = col['h'] * scale, col['w'] * scale
        # DRAW ORDER FIX: PRIMA MENSOLE, POI FERRO
        pdf.set_fill_color(180, 180, 180) 
        if col['mh']:
            for z in col['mh']:
                mz = z * scale
                pdf.rect(current_x + 1, start_y + (120 - mz - (SPESSORE_LEGNO*scale)), w, (SPESSORE_LEGNO*scale), 'F') 
        
        pdf.set_fill_color(0, 0, 0) 
        pdf.rect(current_x, start_y + (120 - h), 1, h, 'F') # SX
        current_x += w + 1
        pdf.rect(current_x, start_y + (120 - h), 1, h, 'F') # DX
        current_x += 0.5 
        
    # PAG 2
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "RIEPILOGO LOGISTICA", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", size=10)
    pdf.cell(45, 10, f"Peso Ferro: {stats['peso_ferro']:.1f} kg", 1)
    pdf.cell(45, 10, f"Peso Legno: {stats['peso_legno']:.1f} kg", 1)
    pdf.cell(45, 10, f"Totale: {stats['peso_tot']:.1f} kg", 1)
    pdf.cell(55, 10, f"Viteria: {stats['viti']} pz", 1, 1)
    pdf.ln(10)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "DISTINTA LEGNO (Mensole)", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 10, "Larghezza", 1)
    pdf.cell(40, 10, "Profondità", 1)
    pdf.cell(40, 10, "Quantità", 1)
    pdf.cell(40, 10, "Metri Totali", 1, 1)
    pdf.set_font("Arial", size=10)
    if not wood_data.empty:
        for index, row in wood_data.iterrows():
            pdf.cell(40, 10, f"{row['Larghezza']:.0f} x {row['Profondità']:.0f}", 1)
            pdf.cell(40, 10, f"{row['Pezzi']}", 1)
            pdf.cell(40, 10, f"{row['Metri Totali']:.1f} m", 1, 1)
    pdf.ln(10)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "DISTINTA FERRO (Fianchi)", 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 10, "Altezza", 1)
    pdf.cell(40, 10, "Profondità", 1)
    pdf.cell(40, 10, "Quantità", 1)
    pdf.ln()
    pdf.set_font("Arial", size=10)
    if not iron_data.empty:
        for index, row in iron_data.iterrows():
            pdf.cell(40, 10, f"{row['Altezza']:.0f} x {row['Profondità']:.0f}", 1)
            pdf.cell(40, 10, f"{row['Pezzi']}", 1)
            pdf.ln()

    # PAG 3: QUOTATO
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "PROSPETTO QUOTATO (INTERASSE FORI)", 0, 1, 'L', fill=True)
    pdf.ln(15)
    
    start_y = pdf.get_y() + 10
    current_x = 20
    tot_len_cm = sum([c['w'] + (SPESSORE_FERRO*2) for c in cols_data]) 
    
    pdf.line(10, start_y + 120, 200, start_y + 120) 
    
    for col in cols_data:
        h, w = col['h'] * scale, col['w'] * scale
        
        # DRAW ORDER FIX
        pdf.set_fill_color(180, 180, 180) 
        z_centers = []
        if col['mh']:
            for z in col['mh']:
                mz = z * scale
                z_centers.append(z + (SPESSORE_LEGNO/2.0))
                pdf.rect(current_x + 1, start_y + (120 - mz - (SPESSORE_LEGNO*scale)), w, (SPESSORE_LEGNO*scale), 'F') 
        
        pdf.set_fill_color(0, 0, 0) 
        pdf.rect(current_x, start_y + (120 - h), 1, h, 'F') 
        current_x += w + 1
        pdf.rect(current_x, start_y + (120 - h), 1, h, 'F') 
        
        pdf.set_font("Arial", '', 7)
        pdf.set_text_color(0, 0, 0)
        x_quota = current_x - (w/2) - 1
        
        if len(z_centers) > 1:
            for i in range(len(z_centers)-1):
                dist = z_centers[i+1] - z_centers[i]
                y_mid = start_y + 120 - ((z_centers[i] + z_centers[i+1])/2 * scale)
                pdf.set_xy(x_quota - 5, y_mid - 2)
                pdf.cell(10, 4, f"{dist:.1f}", 0, 0, 'C')
        
        pdf.set_xy(current_x - w - 1, start_y + 122)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w+2, 5, f"Mod.{col['letter']}", 0, 1, 'C')
        
        current_x += 5 

    # QUOTA TOTALE IN BASSO
    pdf.draw_dimension_line_horz(20, 20 + (tot_len_cm * scale), start_y + 135, f"LARGHEZZA TOT: {tot_len_cm:.1f} cm")

    pdf.set_y(-20)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 10, "* Le quote interne indicano la distanza (interasse) tra i fori delle mensole.", 0, 1, 'L')

    # PAG 4: PIANTA
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "PIANTA (VISTA DALL'ALTO)", 0, 1, 'L', fill=True)
    pdf.ln(20)
    
    start_x = 20
    start_y = pdf.get_y()
    current_x = start_x
    
    pdf.draw_dimension_line_horz(start_x, start_x + (tot_len_cm * scale), start_y - 10, f"TOT: {tot_len_cm:.1f}")
    
    for col in cols_data:
        w_draw = (col['w'] + (SPESSORE_FERRO*2)) * scale
        d_draw = col['d'] * scale
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        pdf.rect(current_x, start_y, w_draw, d_draw)
        
        pdf.set_xy(current_x, start_y + (d_draw/2) - 2)
        pdf.set_font("Arial", '', 8)
        pdf.cell(w_draw, 4, f"P: {col['d']:.0f}", 0, 0, 'C')
        
        pdf.draw_dimension_line_horz(current_x, current_x + w_draw, start_y + d_draw + 5, f"{col['w']:.0f}")
        current_x += w_draw 

    # --- PAGINE DETTAGLIO SINGOLO MODULO (ZOOMED) ---
    scale_det = 0.35 # AUMENTATA SCALA
    
    for col in cols_data:
        pdf.add_page()
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"DETTAGLIO MODULO {col['letter']}", 0, 1, 'L', fill=True)
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 8, f"Dimensioni: {col['w']} (L) x {col['h']} (H) x {col['d']} (P) cm  |  {col['r']} Mensole", 0, 1, 'L')
        pdf.ln(10)
        
        base_y = pdf.get_y() + 200 # Spazio aumentato
        center_x = 105 
        
        # VISTA FRONTALE (SX)
        w_front = col['w'] * scale_det
        h_front = col['h'] * scale_det
        x_front = center_x - w_front - 20 # Spostato più a sinistra
        
        # Disegno Frontale (Ordine Corretto)
        z_vals = [] 
        if col['mh']:
            for z in col['mh']:
                z_vals.append(z + (SPESSORE_LEGNO/2.0))
                mz = z * scale_det
                pdf.set_fill_color(180,180,180)
                pdf.rect(x_front + 1, base_y - mz - (SPESSORE_LEGNO*scale_det), w_front, (SPESSORE_LEGNO*scale_det), 'F')
        
        pdf.set_fill_color(0,0,0)
        pdf.rect(x_front, base_y - h_front, 1, h_front, 'F')
        pdf.rect(x_front + w_front, base_y - h_front, 1, h_front, 'F')
        
        pdf.set_xy(x_front, base_y - h_front - 5)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_front, 5, "VISTA FRONTALE", 0, 0, 'C')
        pdf.draw_dimension_line_horz(x_front, x_front + w_front, base_y + 5, f"L: {col['w']:.0f}")

        # ASSE CENTRALE
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
            pdf.line(line_x - 1, y_curr, line_x + 1, y_curr)
            pdf.line(line_x - 1, y_next, line_x + 1, y_next)
            dist = val_next - val_curr
            if dist > 2: 
                mid_y_quota = (y_curr + y_next) / 2
                pdf.set_xy(line_x + 2, mid_y_quota - 2)
                pdf.cell(10, 4, f"{dist:.1f}", 0, 0, 'L')

        # VISTA LATERALE (DX)
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
                pdf.ellipse(x_hole-0.5, y_hole-0.5, 1, 1, 'F')
        
        pdf.set_xy(x_side, base_y - h_side - 5)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_side, 5, "VISTA LATERALE", 0, 0, 'C')
        pdf.draw_dimension_line_horz(x_side, x_side + w_side, base_y + 5, f"P: {col['d']:.0f}")

    # --- PAGINE ESECUTIVI ---
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "ESECUTIVI DI TAGLIO (FERRO)", 0, 1, 'L', fill=True)
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

# --- 4. DXF ENGINE ---
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

# --- 5. 3D & STL ---
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

# --- 6. LOADING ---
def load_default_if_exists():
    if 'data_loaded' in st.session_state: return
    if os.path.exists("default.json"):
        try:
            with open("default.json", "r") as f:
                data = json.load(f)
                apply_json_data(data)
        except: pass
    st.session_state.data_loaded = True

def apply_json_data(data):
    st.session_state['project_name'] = data.get('project_name', 'Progetto')
    st.session_state['num_colonne'] = data.get('num_colonne', 2)
    for i, col in enumerate(data.get('cols', [])):
        st.session_state[f"w_{i}"] = col.get('w', 60)
        st.session_state[f"h_{i}"] = col.get('h', 200)
        st.session_state[f"d_{i}"] = col.get('d', 30)
        st.session_state[f"r_{i}"] = col.get('r', 4)
        st.session_state[f"man_{i}"] = col.get('manual', False)
        if 'man_heights' in col:
            for j, val in enumerate(col['man_heights']):
                st.session_state[f"h_shelf_{i}_{j}"] = val

def load_user_file(f):
    if f is None: return
    if 'last_loaded_file' in st.session_state and st.session_state.last_loaded_file == f.name: return
    try:
        data = json.load(f)
        apply_json_data(data)
        st.session_state.last_loaded_file = f.name
        st.success("Caricato!")
    except Exception as e: st.error(f"Errore: {e}")

# --- 7. SIDEBAR ---
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
    f = st.file_uploader("Carica JSON", type=["json"])
    if f: load_user_file(f)
    
    st.header("📐 Moduli")
    if 'num_colonne' not in st.session_state: st.session_state['num_colonne'] = 2
    num_colonne = st.number_input("Quantità Moduli", min_value=1, max_value=10, key="num_colonne")
    
    dati_colonne = []
    parts_list = [] 
    wood_list = []  
    iron_stats_list = []

    for i in range(num_colonne):
        module_letter = chr(65 + i)
        with st.expander(f"Modulo {module_letter}", expanded=False):
            c1, c2 = st.columns(2)
            def_w = st.session_state.get(f"w_{i}", 60)
            def_h = st.session_state.get(f"h_{i}", 200)
            def_d = st.session_state.get(f"d_{i}", 30)
            def_r = st.session_state.get(f"r_{i}", 4)
            def_man = st.session_state.get(f"man_{i}", False)
            
            w = c1.number_input("L", 30, 200, value=def_w, key=f"w_{i}")
            d = c2.number_input("P", 20, 100, value=def_d, key=f"d_{i}")
            c3, c4 = st.columns(2)
            h = c3.number_input("H", 50, 400, value=def_h, key=f"h_{i}")
            r = c4.number_input("Rip", 1, 20, value=def_r, key=f"r_{i}")
            
            is_manual = st.checkbox("Libera", value=def_man, key=f"man_{i}")
            mh = []
            z_shelves = []
            if is_manual:
                step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
                for k in range(r):
                    def_shelf = int(k*step)
                    if k == r-1 and r > 1: def_shelf = int(h - SPESSORE_LEGNO)
                    saved = st.session_state.get(f"h_shelf_{i}_{k}", def_shelf)
                    val = st.number_input(f"M {k+1}", value=saved, key=f"h_shelf_{i}_{k}")
                    mh.append(val)
                z_shelves = [float(x) for x in mh]
            else:
                if r == 1: z_shelves = [0.0]
                else:
                    step = (h - SPESSORE_LEGNO)/(r-1)
                    z_shelves = [n*step for n in range(r)]
            
            dati_colonne.append({"w":w, "h":h, "d":d, "r":r, "man":is_manual, "mh":z_shelves, "letter": module_letter})
            
            holes_coords = []
            for z in z_shelves:
                cy = z + (SPESSORE_LEGNO / 2.0) 
                holes_coords.append((OFFSET_LATERALI, cy)) 
                holes_coords.append((d / 2.0, cy))         
                holes_coords.append((d - OFFSET_LATERALI, cy)) 
            
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_SX", "holes": holes_coords})
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_DX", "holes": holes_coords})
            iron_stats_list.append({"Altezza": h, "Profondità": d}) 
            iron_stats_list.append({"Altezza": h, "Profondità": d})
            for _ in range(r): wood_list.append({"w": w, "d": d})

    # --- 3D PLOT ---
    fig = go.Figure()
    cx = 0 
    for dc in dati_colonne:
        lbl = f"Mod {dc['letter']}"
        fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', f"Ferro SX {lbl}"))
        cx += SPESSORE_FERRO
        for idx, z in enumerate(dc["mh"]):
            fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, '#D2B48C', f"Piano {idx+1} {lbl}"))
        cx += dc["w"]
        fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], '#101010', f"Ferro DX {lbl}"))
        cx += SPESSORE_FERRO

    # --- EXPORT FOOTER ---
    st.divider()
    st.header("SALVA / ESPORTA")
    
    ts = get_timestamp_string()
    prj = st.session_state['project_name']
    fname_json = f"{prj}_{ts}.json"
    fname_stl = f"{prj}_{ts}.stl"
    
    cols_to_save = []
    for dc in dati_colonne:
         cols_to_save.append({"w": dc['w'], "h": dc['h'], "d": dc['d'], "r": dc['r'], "manual": dc['man'], "man_heights": dc['mh']})
    proj_data = {"project_name": prj, "num_colonne":st.session_state.num_colonne, "cols":cols_to_save}

    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj_data), fname_json, "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), fname_stl, "application/octet-stream")
    st.divider()
    st.caption(VERSION)

# --- 9. TABS MAIN ---
tab1, tab2 = st.tabs(["🎥 3D Config", "🏭 ESECUTIVI PRODUZIONE"])

with tab1:
    fig.update_layout(scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(title="H"), aspectmode='data', bgcolor="white"), margin=dict(t=0,b=0,l=0,r=0), height=600)
    st.plotly_chart(fig, width="stretch")

with tab2:
    st.markdown(f"### Distinta Materiali - {prj}")
    
    vol_ferro = sum([p['w'] * p['h'] * SPESSORE_FERRO for p in parts_list])
    peso_ferro = (vol_ferro * PESO_SPECIFICO_FERRO) / 1000.0
    vol_legno = sum([w['w'] * w['d'] * SPESSORE_LEGNO for w in wood_list])
    peso_legno = (vol_legno * PESO_SPECIFICO_LEGNO) / 1000.0
    num_viti = len(wood_list) * 6
    stats = {"peso_ferro": peso_ferro, "peso_legno": peso_legno, "peso_tot": peso_ferro + peso_legno, "viti": num_viti}
    
    df_legno = pd.DataFrame(wood_list)
    distinta_legno_pdf = pd.DataFrame()
    if not df_legno.empty:
        df_legno['Quantità'] = 1
        distinta_legno_pdf = df_legno.groupby(['w', 'd']).count().reset_index()
        distinta_legno_pdf['Metri Totali'] = (distinta_legno_pdf['w'] * distinta_legno_pdf['Quantità']) / 100.0
        distinta_legno_pdf.columns = ['Larghezza', 'Profondità', 'Pezzi', 'Metri Totali']
        
    df_ferro = pd.DataFrame(iron_stats_list)
    distinta_ferro_pdf = pd.DataFrame()
    if not df_ferro.empty:
        df_ferro['Quantità'] = 1
        distinta_ferro_pdf = df_ferro.groupby(['Altezza', 'Profondità']).count().reset_index()
        distinta_ferro_pdf.columns = ['Altezza', 'Profondità', 'Pezzi']
    
    c_info1, c_info2, c_info3, c_info4 = st.columns(4)
    c_info1.metric("Peso Totale", f"{stats['peso_tot']:.1f} kg")
    c_info2.metric("Peso Ferro", f"{stats['peso_ferro']:.1f} kg")
    c_info3.metric("Peso Legno", f"{stats['peso_legno']:.1f} kg")
    c_info4.metric("Viteria", f"{num_viti} pz")
    
    fname_pdf = f"{prj}_{ts}_SchedaTecnica.pdf"
    if st.button("📄 GENERA SCHEDA TECNICA PDF", type="primary", use_container_width=True):
        pdf_bytes = generate_pdf_report(prj, parts_list, distinta_legno_pdf, distinta_ferro_pdf, stats, dati_colonne)
        st.download_button("📥 SCARICA PDF", pdf_bytes, fname_pdf, "application/pdf")
    
    st.divider()
    
    c_sx, c_dx = st.columns(2)
    with c_sx:
        st.subheader("🌲 Distinta Legno")
        if not df_legno.empty: st.dataframe(distinta_legno_pdf, hide_index=True, use_container_width=True)
        else: st.info("Nessuna mensola.")
            
    with c_dx:
        st.subheader("⛓️ Distinta Ferro")
        if not distinta_ferro_pdf.empty: st.dataframe(distinta_ferro_pdf, hide_index=True, use_container_width=True)
    
    st.divider()
    st.subheader("📦 Esecutivi Taglio (Anteprima Completa)")
    
    fname_dxf_full = f"{prj}_{ts}_Tutto.dxf"
    dxf_full = generate_full_dxf(parts_list, prj)
    st.download_button("📦 SCARICA DXF UNICO (Tutti i pezzi)", dxf_full, fname_dxf_full, "application/dxf", type="primary", use_container_width=True)
    
    st.write("##")
    
    fig_all = go.Figure()
    cursor_y_plot = 0
    gap_plot = 30 
    for idx, part in enumerate(parts_list):
        dim_x, dim_y = part['h'], part['w']
        fig_all.add_shape(type="rect", x0=0, y0=cursor_y_plot, x1=dim_x, y1=cursor_y_plot+dim_y, line=dict(color="#E0E0E0", width=2))
        x_holes = [hy for hx, hy in part['holes']] 
        y_holes = [cursor_y_plot + hx for hx, hy in part['holes']] 
        fig_all.add_trace(go.Scatter(x=x_holes, y=y_holes, mode='markers', marker=dict(color='#00FFFF', size=6), hoverinfo='skip'))
        fig_all.add_annotation(x=dim_x/2, y=cursor_y_plot + dim_y/2, text=part['lbl'], showarrow=False, font=dict(size=14, color="white"))
        
        unique_x = sorted(list(set(x_holes)))
        for i in range(len(unique_x) - 1):
            dist = unique_x[i+1] - unique_x[i]
            mid_x = (unique_x[i] + unique_x[i+1]) / 2
            fig_all.add_annotation(x=mid_x, y=cursor_y_plot - 5, text=f"| {dist:.1f} |", showarrow=False, font=dict(size=10, color="#AAAAAA"))

        cursor_y_plot += dim_y + gap_plot

    fig_all.update_layout(
        xaxis=dict(title="Lunghezza (cm)", showgrid=True, gridcolor='#555', gridwidth=2, dtick=50, minor=dict(ticklen=5, tickcolor='#333', dtick=10, showgrid=True, gridcolor='#333', gridwidth=1), zeroline=False),
        yaxis=dict(title="Pezzi in sequenza", showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1),
        height=600, margin=dict(l=10, r=10, t=10, b=10),
        dragmode="pan", showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
    )
    config_plot = {'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d']}
    st.plotly_chart(fig_all, width="stretch", config=config_plot)

    with st.expander("📂 Scarica DXF Pezzi Singoli (Opzionale)"):
        for idx, part in enumerate(parts_list):
            c_name, c_down = st.columns([4, 1])
            c_name.write(f"**{part['lbl']}** ({part['h']}x{part['w']} cm)")
            dxf_single = generate_single_dxf(part, prj)
            c_down.download_button("⬇️ DXF", dxf_single, f"{part['lbl']}.dxf", "application/dxf", key=f"dxf_{idx}")
