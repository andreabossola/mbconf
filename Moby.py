
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 
from datetime import datetime

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby v0.9 (Reorder Fix)")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        c_logo, c_title = st.columns([1, 4])
        try: c_logo.image("logo.png", width=150)
        except: pass
        c_title.markdown("## 🔒 Area Riservata - v0.9")
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
VERSION = "v0.9.1 Reorder Fixed"
COPYRIGHT = "© Andrea Bossola 2025"
stl_triangles = [] 

# --- UTILITY ---
def get_timestamp_string(): return datetime.now().strftime("%Y%m%d_%H%M")
def clean_filename(name): return "".join([c if c.isalnum() else "_" for c in name])

# --- GESTIONE STATO ORDINE MODULI ---
def init_module_order(n):
    # Se non esiste l'ordine, crealo sequenziale [0, 1, 2...]
    if 'module_order' not in st.session_state:
        st.session_state.module_order = list(range(n))
    
    # Se cambiamo numero colonne, adattiamo la lista
    current = st.session_state.module_order
    if n > len(current):
        # Aggiungi i nuovi ID in coda
        next_id = max(current) + 1 if current else 0
        for _ in range(n - len(current)):
            current.append(next_id)
            next_id += 1
    elif n < len(current):
        # Taglia la lista mantenendo l'ordine attuale
        st.session_state.module_order = current[:n]

def swap_modules(pos_idx, direction):
    # direction: -1 (su/sx), +1 (giu/dx)
    order = st.session_state.module_order
    new_idx = pos_idx + direction
    
    if 0 <= new_idx < len(order):
        # Scambia gli ID nella lista ordine
        order[pos_idx], order[new_idx] = order[new_idx], order[pos_idx]
        st.session_state.module_order = order

# --- 3. NESTING ENGINE ---
class Sheet:
    def __init__(self, w, h, id):
        self.w, self.h, self.id = w, h, id
        self.items = []
        self.cursor_x = 0
        self.cursor_y = 0
        self.row_h = 0
        self.used_area = 0 

    def add(self, item):
        margin = 1.0 
        iw, ih = item['w'] + margin, item['h'] + margin
        if self.cursor_x + iw > self.w:
            self.cursor_x, self.cursor_y, self.row_h = 0, self.cursor_y + self.row_h, 0
        if self.cursor_y + ih > self.h: return False
        
        item['x_pos'], item['y_pos'] = self.cursor_x, self.cursor_y
        self.items.append(item)
        self.used_area += item['w'] * item['h']
        self.cursor_x += iw
        self.row_h = max(self.row_h, ih)
        return True

def run_nesting(parts, sheet_w, sheet_h):
    opt_parts = []
    for p in parts:
        if p['h'] > sheet_h and p['h'] <= sheet_w:
            p.update({'w':p['h'], 'h':p['w'], 'holes':[(y,x) for x,y in p['holes']], 'rotated':True})
        opt_parts.append(p)
    parts_sorted = sorted(opt_parts, key=lambda x: x['h'], reverse=True)
    sheets = [Sheet(sheet_w, sheet_h, 1)]
    for p in parts_sorted:
        if not sheets[-1].add(p):
            sheets.append(Sheet(sheet_w, sheet_h, len(sheets)+1))
            sheets[-1].add(p)
    return sheets

# --- 4. DXF GENERATOR ---
def generate_dxf(sheets, sheet_w, sheet_h, project_name):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for name, col in [('TAGLIO',1), ('FORI',5), ('BORDO_LASTRA',7), ('TESTO',3)]:
        doc.layers.new(name=name, dxfattribs={'color': col})
    
    ox = 0 
    date_str = datetime.now().strftime("%d/%m/%Y")
    for s in sheets:
        msp.add_lwpolyline([(ox,0), (sheet_w+ox,0), (sheet_w+ox,sheet_h), (ox,sheet_h), (ox,0)], dxfattribs={'layer': 'BORDO_LASTRA'})
        t = msp.add_text(f"LASTRA {s.id} | {project_name} | {date_str}", dxfattribs={'layer': 'TESTO', 'height': 4.0})
        t.dxf.insert = (5+ox, sheet_h - 10)
        for i in s.items:
            x, y = i['x_pos']+ox, i['y_pos']
            msp.add_lwpolyline([(x,y), (x+i['w'],y), (x+i['w'],y+i['h']), (x,y+i['h']), (x,y)], dxfattribs={'layer': 'TAGLIO'})
            for hx, hy in i['holes']: msp.add_circle((x+hx, y+hy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
            lbl = msp.add_text(i['lbl'] + (" (R)" if i.get('rotated') else ""), dxfattribs={'layer': 'TESTO', 'height': 2.5})
            lbl.dxf.insert = (x+2, y+2)
        ox += sheet_w + 20 
    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

# --- 5. LOAD CONFIG ---
def load_config(f):
    try:
        data = json.load(f)
        st.session_state['project_name'] = data.get('project_name', 'Progetto')
        
        # Carica numero colonne e aggiorna lo stato PRIMA del render
        nc = data.get('num_colonne', 1)
        st.session_state['num_colonne'] = nc
        
        # Reset Ordine
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
        st.success("Caricato!")
    except: st.error("Errore File")

# --- 6. INTERFACCIA ---
with st.sidebar:
    try: st.image("logo.png", width=200) 
    except: st.markdown("## MOBY")
    
    # --- FIX INPUT NOME PROGETTO ---
    if 'project_name' not in st.session_state: st.session_state['project_name'] = "Progetto"
    # Usiamo direttamente key, senza value, per evitare conflitti
    st.text_input("Nome Progetto", key='project_name_input', value=st.session_state['project_name'])
    st.session_state['project_name'] = clean_filename(st.session_state['project_name_input'])
    
    st.divider()
    
    f = st.file_uploader("Carica JSON", type=["json"])
    if f: load_config(f)
    st.divider()
    
    st.header("📐 Moduli")
    
    # --- FIX INPUT NUM COLONNE ---
    if 'num_colonne' not in st.session_state: st.session_state['num_colonne'] = 2
    # Rimuoviamo il parametro value, lasciamo gestire tutto allo stato
    num_colonne = st.number_input("Quantità Moduli", min_value=1, max_value=10, key="num_colonne")
    
    # Aggiorna la lista dell'ordine in base al numero colonne
    init_module_order(num_colonne)
    
    dati_colonne_ordinate = []
    lista_pezzi_ferro = [] 

    # Ciclo sull'ordine visuale
    for pos_index, module_id in enumerate(st.session_state.module_order):
        module_letter = chr(65 + module_id) # A, B, C...
        
        # Recupero valori di default se non esistono nel session state
        def_w = st.session_state.get(f"w_{module_id}", 60)
        def_h = st.session_state.get(f"h_{module_id}", 200)
        def_d = st.session_state.get(f"d_{module_id}", 30)
        def_r = st.session_state.get(f"r_{module_id}", 4)
        def_man = st.session_state.get(f"man_{module_id}", False)
        
        with st.expander(f"POSIZIONE {pos_index+1} (Modulo {module_letter})", expanded=False):
            # Pulsanti Spostamento
            c_move1, c_move2 = st.columns(2)
            if pos_index > 0:
                if c_move1.button(f"⬆️ Sposta Su", key=f"btn_up_{module_id}"):
                    swap_modules(pos_index, -1)
                    st.rerun()
            if pos_index < num_colonne - 1:
                if c_move2.button(f"⬇️ Sposta Giù", key=f"btn_down_{module_id}"):
                    swap_modules(pos_index, 1)
                    st.rerun()

            c1, c2 = st.columns(2)
            # NOTA: Qui uso 'value=def_w' la prima volta, ma Streamlit gestisce la key
            # Se la key esiste già, 'value' viene ignorato (comportamento corretto).
            w = c1.number_input("Largh.", 30, 200, def_w, key=f"w_{module_id}")
            d = c2.number_input("Prof.", 20, 100, def_d, key=f"d_{module_id}")
            c3, c4 = st.columns(2)
            h = c3.number_input("Alt.", 50, 400, def_h, key=f"h_{module_id}")
            r = c4.number_input("Ripiani", 1, 20, def_r, key=f"r_{module_id}")
            
            is_manual = st.checkbox("Posizione Libera", value=def_man, key=f"man_{module_id}")
            mh = []
            
            z_shelves = []
            if is_manual:
                step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
                for k in range(r):
                    def_shelf_val = int(k*step)
                    if k == r-1 and r > 1: def_shelf_val = int(h - SPESSORE_LEGNO)
                    # Recupera valore salvato se esiste
                    saved_shelf = st.session_state.get(f"h_shelf_{module_id}_{k}", def_shelf_val)
                    val = st.number_input(f"M {k+1}", value=saved_shelf, key=f"h_shelf_{module_id}_{k}")
                    mh.append(val)
                z_shelves = [float(x) for x in mh]
            else:
                if r == 1: z_shelves = [0.0]
                else:
                    step = (h - SPESSORE_LEGNO)/(r-1)
                    z_shelves = [n*step for n in range(r)]
            
            dati_colonne_ordinate.append({
                "w":w, "h":h, "d":d, "r":r, "man":is_manual, "mh":z_shelves, 
                "letter": module_letter
            })

            holes_coords = []
            for z in z_shelves:
                cy = z + (SPESSORE_LEGNO / 2.0) 
                holes_coords.append((OFFSET_LATERALI, cy)) 
                holes_coords.append((d / 2.0, cy))         
                holes_coords.append((d - OFFSET_LATERALI, cy)) 
            
            # Label univoca per nesting
            lbl_suffix = f"{module_letter}"
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M_{lbl_suffix}_SX", "holes": holes_coords, "rotated": False})
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M_{lbl_suffix}_DX", "holes": holes_coords, "rotated": False})

    st.markdown("---")
    st.caption(f"{COPYRIGHT} | {VERSION}")

# --- 7. VISUALIZZAZIONE 3D ---
fig = go.Figure()
cx = 0 
C_WOOD, C_IRON = '#D2B48C', '#101010'

def add_stl(x,y,z,dx,dy,dz):
    v = [[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],[x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]]
    idx = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[2,3,7],[2,7,6],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    for t in idx: stl_triangles.append((v[t[0]],v[t[1]],v[t[2]]))

def draw(x,y,z,dx,dy,dz,col,name):
    add_stl(x,y,z,dx,dy,dz)
    xv, yv, zv = [x, x+dx, x+dx, x]*2, [y, y, y+dy, y+dy]*2, [z]*4 + [z+dz]*4
    I,J,K = [0,0,4,4,0,0,2,2,3,3,1,1], [1,2,5,6,1,5,3,7,0,4,2,6], [2,3,6,7,5,4,7,6,4,7,6,5]
    return go.Mesh3d(x=xv, y=yv, z=zv, i=I, j=J, k=K, color=col, opacity=1, flatshading=True, name=name, lighting=dict(ambient=0.6, diffuse=0.8), hoverinfo='name')

for dc in dati_colonne_ordinate:
    lbl = f"Mod {dc['letter']}"
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro SX {lbl}"))
    cx += SPESSORE_FERRO
    for idx, z in enumerate(dc["mh"]):
        fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, C_WOOD, f"Piano {idx+1} {lbl}"))
    cx += dc["w"]
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro DX {lbl}"))
    cx += SPESSORE_FERRO

def get_bin_stl(tris):
    out = io.BytesIO()
    out.write(b'\0'*80 + struct.pack('<I', len(tris)))
    for p in tris: out.write(struct.pack('<ffffffffffffH', 0,0,0, *p[0], *p[1], *p[2], 0))
    return out.getvalue()

ts = get_timestamp_string()
prj = st.session_state['project_name']
fname_json = f"{prj}_{ts}.json"
fname_stl = f"{prj}_{ts}.stl"
fname_dxf = f"{prj}_{ts}_Taglio.dxf"

# Salvataggio dati ordinati per ID
cols_to_save = [None] * num_colonne
for dc in dati_colonne_ordinate:
    idx = ord(dc['letter']) - 65
    if idx < num_colonne:
         cols_to_save[idx] = {
             "w": dc['w'], "h": dc['h'], "d": dc['d'], "r": dc['r'], 
             "manual": dc['man'], "man_heights": dc['mh']
         }
cols_to_save = [c for c in cols_to_save if c is not None]
proj_data = {"project_name": prj, "num_colonne":num_colonne, "cols":cols_to_save}

with st.sidebar:
    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj_data), fname_json, "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), fname_stl, "application/octet-stream")

# --- 8. TABS ---
tab1, tab2 = st.tabs(["🎥 3D Config", "🏭 ESECUTIVI TAGLIO (DXF)"])

with tab1:
    fig.update_layout(scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(title="H"), aspectmode='data', bgcolor="white"), margin=dict(t=0,b=0,l=0,r=0), height=600)
    st.plotly_chart(fig, width="stretch")

with tab2:
    st.markdown(f"### Esecutivi Produzione - {prj}")
    
    col_input1, col_input2, col_input3 = st.columns(3)
    sheet_w = col_input1.number_input("Lungh. Lastra (cm)", value=300)
    sheet_h = col_input2.number_input("Largh. Lastra (cm)", value=150)
    cost_sheet = col_input3.number_input("Costo Lastra (€)", value=120.0)
    
    if len(lista_pezzi_ferro) > 0:
        sheets_result = run_nesting(lista_pezzi_ferro, sheet_w, sheet_h)
        n_sheets = len(sheets_result)
        tot_cost = n_sheets * cost_sheet
        waste_pct = ((n_sheets*sheet_w*sheet_h - sum([s.used_area for s in sheets_result])) / (n_sheets*sheet_w*sheet_h)) * 100 if n_sheets > 0 else 0
        
        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("Lastre", n_sheets)
        c_res2.metric("Costo", f"€ {tot_cost:.2f}")
        c_res3.metric("Sfrido", f"{waste_pct:.1f} %")
        st.divider()
        
        for s in sheets_result:
            st.subheader(f"Lastra {s.id}")
            shapes = [dict(type="rect", x0=0, y0=0, x1=sheet_w, y1=sheet_h, line=dict(color="black"), fillcolor="white")]
            annotations = []
            for item in s.items:
                shapes.append(dict(type="rect", x0=item['x_pos'], y0=item['y_pos'], x1=item['x_pos']+item['w'], y1=item['y_pos']+item['h'], line=dict(color="red", width=2), fillcolor="rgba(255,0,0,0.1)"))
                lbl = item['lbl'] + (" (R)" if item.get('rotated') else "")
                annotations.append(dict(x=item['x_pos']+item['w']/2, y=item['y_pos']+item['h']/2, text=lbl, showarrow=False, font=dict(color="black", size=10)))
                for hx, hy in item['holes']:
                    cx, cy = item['x_pos'] + hx, item['y_pos'] + hy
                    shapes.append(dict(type="circle", xref="x", yref="y", x0=cx-1, y0=cy-1, x1=cx+1, y1=cy+1, line_color="blue", fillcolor="blue"))

            fig_2d = go.Figure()
            fig_2d.update_layout(shapes=shapes, annotations=annotations, xaxis=dict(range=[-10, sheet_w+10], showgrid=True), yaxis=dict(range=[-10, sheet_h+10], scaleanchor="x"), height=500, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_2d, width="stretch", key=f"sheet_preview_{s.id}")
            
            fname_lastra = f"{prj}_{ts}_Lastra{s.id}.dxf"
            dxf_single = generate_dxf([s], sheet_w, sheet_h, prj)
            st.download_button(f"💾 DXF Lastra {s.id}", dxf_single, fname_lastra, "application/dxf", key=f"btn_{s.id}")
            
        st.divider()
        dxf_full = generate_dxf(sheets_result, sheet_w, sheet_h, prj)
        st.download_button("📦 SCARICA TUTTO (Tutte le Lastre)", dxf_full, fname_dxf, "application/dxf", type="primary")
