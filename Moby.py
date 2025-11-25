
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 
import pandas as pd
from datetime import datetime

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby v1.0 Master")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        c_logo, c_title = st.columns([1, 4])
        try: c_logo.image("logo.png", width=150)
        except: pass
        c_title.markdown("## 🔒 Area Riservata - v1.0 Master")
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

# --- 2. COSTANTI FISICHE ---
SPESSORE_LEGNO = 4.0  # cm
SPESSORE_FERRO = 0.3  # cm (3mm)
DIAMETRO_FORO = 0.6   # cm
OFFSET_LATERALI = 3.0 # cm
PESO_SPECIFICO_FERRO = 7.85 # g/cm3
PESO_SPECIFICO_LEGNO = 0.70 # g/cm3 (Media truciolare/multistrato)

VERSION = "v1.0 Master"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- UTILITY ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- GESTIONE STATO ---
def init_state():
    if 'module_order' not in st.session_state:
        st.session_state.module_order = [0, 1]
    if 'num_colonne' not in st.session_state:
        st.session_state.num_colonne = 2
    if 'last_loaded_file' not in st.session_state:
        st.session_state.last_loaded_file = None
    for mod_id in st.session_state.module_order:
        if f"w_{mod_id}" not in st.session_state:
            st.session_state[f"w_{mod_id}"] = 60
            st.session_state[f"h_{mod_id}"] = 200
            st.session_state[f"d_{mod_id}"] = 30
            st.session_state[f"r_{mod_id}"] = 4
            st.session_state[f"man_{mod_id}"] = False

def update_num_modules():
    n = st.session_state.num_colonne
    current = st.session_state.module_order
    if n > len(current):
        next_id = max(current) + 1 if current else 0
        for _ in range(n - len(current)):
            st.session_state.module_order.append(next_id)
            next_id += 1
    elif n < len(current):
        st.session_state.module_order = current[:n]
    init_state() 

def swap_modules(idx1, idx2):
    order = st.session_state.module_order
    order[idx1], order[idx2] = order[idx2], order[idx1]
    st.session_state.module_order = order

# --- 3. DXF ENGINE ---
def create_dxf_doc():
    doc = ezdxf.new()
    for name, col in [('TAGLIO',1), ('FORI',5), ('INFO',3)]:
        doc.layers.new(name=name, dxfattribs={'color': col})
    return doc

def draw_part_on_dxf(msp, part, offset_x, offset_y, project_name):
    # part: {w, h, holes, lbl} - Sempre orizzontale (h=lunghezza, w=altezza foglio)
    dim_x = part['h'] # Lunghezza pezzo (ex altezza colonna)
    dim_y = part['w'] # Larghezza pezzo (ex profondità)
    
    # Rettangolo Taglio
    msp.add_lwpolyline([
        (offset_x, offset_y), 
        (offset_x+dim_x, offset_y), 
        (offset_x+dim_x, offset_y+dim_y), 
        (offset_x, offset_y+dim_y), 
        (offset_x, offset_y)
    ], dxfattribs={'layer': 'TAGLIO'})
    
    # Fori
    for hx, hy in part['holes']:
        # hx era profondità, hy era altezza. Ruotato: cx = hy, cy = hx
        cx = offset_x + hy
        cy = offset_y + hx
        msp.add_circle((cx, cy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
    
    # Info Testo (Layer INFO)
    date_str = datetime.now().strftime("%d/%m/%y")
    info_txt = f"{part['lbl']} | {project_name} | {date_str}"
    t = msp.add_text(info_txt, dxfattribs={'layer': 'INFO', 'height': 2.5})
    t.dxf.insert = (offset_x + 2, offset_y + 2)
    
    return dim_x # Ritorna la lunghezza occupata

def generate_single_dxf(part, project_name):
    doc = create_dxf_doc()
    msp = doc.modelspace()
    draw_part_on_dxf(msp, part, 0, 0, project_name)
    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

def generate_full_dxf(parts, project_name):
    doc = create_dxf_doc()
    msp = doc.modelspace()
    cursor_y = 0
    gap = 10
    
    for part in parts:
        draw_part_on_dxf(msp, part, 0, cursor_y, project_name)
        cursor_y += part['w'] + gap # Scendiamo giù
        
    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

# --- 4. LOGICA 3D E STL ---
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

# --- 5. CARICAMENTO ---
def load_config(f):
    if f is None: return
    if st.session_state.last_loaded_file == f.name: return
    try:
        data = json.load(f)
        st.session_state['project_name'] = data.get('project_name', 'Progetto')
        nc = data.get('num_colonne', 1)
        st.session_state['num_colonne'] = nc
        st.session_state.module_order = list(range(nc))
        for i, col in enumerate(data.get('cols', [])):
            st.session_state[f"w_{i}"] = col.get('w', 60)
            st.session_state[f"h_{i}"] = col.get('h', 200)
            st.session_state[f"d_{i}"] = col.get('d', 30)
            st.session_state[f"r_{i}"] = col.get('r', 4)
            st.session_state[f"man_{i}"] = col.get('manual', False)
            if 'man_heights' in col:
                for j, val in enumerate(col['man_heights']):
                    st.session_state[f"h_shelf_{i}_{j}"] = val
        st.session_state.last_loaded_file = f.name
        st.success("Caricato!")
    except Exception as e: st.error(f"Errore File: {e}")

# --- 6. INTERFACCIA ---
init_state()

with st.sidebar:
    try: st.image("logo.png", width=200) 
    except: st.markdown("## MOBY")
    
    if 'project_name' not in st.session_state: st.session_state['project_name'] = "Progetto"
    st.text_input("Nome Progetto", key='project_name_input', value=st.session_state['project_name'])
    st.session_state['project_name'] = clean_filename(st.session_state['project_name_input'])
    st.divider()
    f = st.file_uploader("Carica JSON", type=["json"])
    if f: load_config(f)
    st.divider()
    st.header("📐 Moduli")
    st.number_input("Quantità Moduli", min_value=1, max_value=10, key="num_colonne", on_change=update_num_modules)
    
    dati_colonne_ordinate = []
    parts_list = [] # Per DXF
    wood_list = []  # Per Distinta Legno

    for pos_index, module_id in enumerate(st.session_state.module_order):
        module_letter = chr(65 + module_id)
        def_w = st.session_state.get(f"w_{module_id}", 60)
        def_h = st.session_state.get(f"h_{module_id}", 200)
        def_d = st.session_state.get(f"d_{module_id}", 30)
        def_r = st.session_state.get(f"r_{module_id}", 4)
        def_man = st.session_state.get(f"man_{module_id}", False)
        
        with st.expander(f"POSIZIONE {pos_index+1} (Modulo {module_letter})", expanded=False):
            c_move1, c_move2 = st.columns(2)
            if pos_index > 0:
                if c_move1.button(f"⬅️ SX", key=f"btn_up_{module_id}"):
                    swap_modules(pos_index, -1)
                    st.rerun()
            if pos_index < len(st.session_state.module_order) - 1:
                if c_move2.button(f"➡️ DX", key=f"btn_down_{module_id}"):
                    swap_modules(pos_index, 1)
                    st.rerun()

            c1, c2 = st.columns(2)
            w = c1.number_input("L", 30, 200, key=f"w_{module_id}")
            d = c2.number_input("P", 20, 100, key=f"d_{module_id}")
            c3, c4 = st.columns(2)
            h = c3.number_input("H", 50, 400, key=f"h_{module_id}")
            r = c4.number_input("Rip", 1, 20, key=f"r_{module_id}")
            
            is_manual = st.checkbox("Libera", key=f"man_{module_id}")
            mh = []
            z_shelves = []
            if is_manual:
                step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
                for k in range(r):
                    def_shelf_val = int(k*step)
                    if k == r-1 and r > 1: def_shelf_val = int(h - SPESSORE_LEGNO)
                    if f"h_shelf_{module_id}_{k}" not in st.session_state:
                        st.session_state[f"h_shelf_{module_id}_{k}"] = def_shelf_val
                    val = st.number_input(f"M {k+1}", key=f"h_shelf_{module_id}_{k}")
                    mh.append(val)
                z_shelves = [float(x) for x in mh]
            else:
                if r == 1: z_shelves = [0.0]
                else:
                    step = (h - SPESSORE_LEGNO)/(r-1)
                    z_shelves = [n*step for n in range(r)]
            
            dati_colonne_ordinate.append({"w":w, "h":h, "d":d, "r":r, "man":is_manual, "mh":z_shelves, "letter": module_letter})

            # RACCOLTA DATI PER PRODUZIONE
            # 1. VITI & FORI
            holes_coords = []
            for z in z_shelves:
                cy = z + (SPESSORE_LEGNO / 2.0) 
                holes_coords.append((OFFSET_LATERALI, cy)) 
                holes_coords.append((d / 2.0, cy))         
                holes_coords.append((d - OFFSET_LATERALI, cy)) 
            
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_SX", "holes": holes_coords})
            parts_list.append({"w": d, "h": h, "lbl": f"Mod_{module_letter}_DX", "holes": holes_coords})
            
            # 2. LEGNO
            for _ in range(r):
                wood_list.append({"w": w, "d": d})

    st.markdown("---")
    st.caption(f"{COPYRIGHT} | {VERSION}")

# --- 7. VISUALIZZATORE 3D ---
fig = go.Figure()
cx = 0 
C_WOOD, C_IRON = '#D2B48C', '#101010'

for dc in dati_colonne_ordinate:
    lbl = f"Mod {dc['letter']}"
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro SX {lbl}"))
    cx += SPESSORE_FERRO
    for idx, z in enumerate(dc["mh"]):
        fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, C_WOOD, f"Piano {idx+1} {lbl}"))
    cx += dc["w"]
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro DX {lbl}"))
    cx += SPESSORE_FERRO

ts = get_timestamp_string()
prj = st.session_state['project_name']
fname_json = f"{prj}_{ts}.json"
fname_stl = f"{prj}_{ts}.stl"
fname_dxf_full = f"{prj}_{ts}_Tutto.dxf"

cols_to_save = [None] * len(dati_colonne_ordinate)
for dc in dati_colonne_ordinate:
    idx = ord(dc['letter']) - 65
    if idx < len(cols_to_save):
         cols_to_save[idx] = {"w": dc['w'], "h": dc['h'], "d": dc['d'], "r": dc['r'], "manual": dc['man'], "man_heights": dc['mh']}
cols_to_save = [c for c in cols_to_save if c is not None]
proj_data = {"project_name": prj, "num_colonne":st.session_state.num_colonne, "cols":cols_to_save}

with st.sidebar:
    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj_data), fname_json, "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), fname_stl, "application/octet-stream")

# --- 8. TABS (PRODUZIONE COMPLETA) ---
tab1, tab2 = st.tabs(["🎥 3D Config", "🏭 ESECUTIVI PRODUZIONE"])

with tab1:
    fig.update_layout(scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(title="H"), aspectmode='data', bgcolor="white"), margin=dict(t=0,b=0,l=0,r=0), height=600)
    st.plotly_chart(fig, width="stretch")

with tab2:
    st.markdown(f"### Distinta Materiali - {prj}")
    
    # --- CALCOLI ---
    # Peso Ferro
    vol_ferro = sum([p['w'] * p['h'] * SPESSORE_FERRO for p in parts_list])
    peso_ferro = (vol_ferro * PESO_SPECIFICO_FERRO) / 1000.0 # kg
    
    # Peso Legno
    vol_legno = sum([w['w'] * w['d'] * SPESSORE_LEGNO for w in wood_list])
    peso_legno = (vol_legno * PESO_SPECIFICO_LEGNO) / 1000.0 # kg
    
    # Viti
    num_viti = len(wood_list) * 6
    
    # Distinta Legno Raggruppata
    df_legno = pd.DataFrame(wood_list)
    df_legno['Quantità'] = 1
    if not df_legno.empty:
        distinta_legno = df_legno.groupby(['w', 'd']).count().reset_index()
        distinta_legno['Metri Lineari'] = (distinta_legno['w'] * distinta_legno['Quantità']) / 100.0
        distinta_legno.columns = ['Larghezza (cm)', 'Profondità (cm)', 'Pezzi (Q.tà)', 'Tot. Metri (L)']
    
    # --- VISUALIZZAZIONE DATI ---
    
    c_info1, c_info2, c_info3, c_info4 = st.columns(4)
    c_info1.metric("Peso Totale", f"{peso_ferro + peso_legno:.1f} kg")
    c_info2.metric("Peso Ferro", f"{peso_ferro:.1f} kg")
    c_info3.metric("Peso Legno", f"{peso_legno:.1f} kg")
    c_info4.metric("Viteria", f"{num_viti} pz")
    
    st.divider()
    
    c_sx, c_dx = st.columns(2)
    
    with c_sx:
        st.subheader("🌲 Distinta Legno (Mensole)")
        if not df_legno.empty:
            st.dataframe(distinta_legno, hide_index=True, use_container_width=True)
        else:
            st.info("Nessuna mensola presente.")
            
    with c_dx:
        st.subheader("⛓️ Distinta Ferro (Fianchi)")
        st.markdown(f"**Totale Pezzi:** {len(parts_list)}")
        dxf_full = generate_full_dxf(parts_list, prj)
        st.download_button("📦 SCARICA DXF UNICO (Tutti i pezzi)", dxf_full, fname_dxf_full, "application/dxf", type="primary", use_container_width=True)

    st.divider()
    st.subheader("📄 Dettaglio Pezzi Ferro (DXF Singoli)")
    
    for idx, part in enumerate(parts_list):
        # Preview 2D (Ruotato orizzontale)
        dim_x = part['h']
        dim_y = part['w']
        
        shapes = [dict(type="rect", x0=0, y0=0, x1=dim_x, y1=dim_y, line=dict(color="black"), fillcolor="rgba(0,0,0,0.05)")]
        for hx, hy in part['holes']:
            cx = hy # Scambio assi per visualizzazione orizzontale
            cy = hx
            shapes.append(dict(type="circle", xref="x", yref="y", x0=cx-1, y0=cy-1, x1=cx+1, y1=cy+1, line_color="blue", fillcolor="blue"))

        fig_2d = go.Figure()
        fig_2d.update_layout(
            title=f"{part['lbl']} ({dim_x} x {dim_y} cm)",
            shapes=shapes, 
            xaxis=dict(range=[-5, dim_x+5], showgrid=True, title="Lunghezza (ex H)"), 
            yaxis=dict(range=[-5, dim_y+5], scaleanchor="x", title="Larghezza (ex P)"), 
            height=150, margin=dict(l=10, r=10, t=30, b=10)
        )
        
        col_p1, col_p2 = st.columns([4, 1])
        col_p1.plotly_chart(fig_2d, width="stretch", key=f"preview_{idx}")
        col_p2.write("##")
        dxf_single = generate_single_dxf(part, prj)
        col_p2.download_button("⬇️ DXF", dxf_single, f"{part['lbl']}.dxf", "application/dxf", key=f"dxf_{idx}")
        col_p2.caption(f"{len(part['holes'])} fori")
        st.divider()
