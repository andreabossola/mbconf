
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 
from datetime import datetime

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby Configurator v0.8")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        # LOGO NELLA PAGINA LOGIN
        c_logo, c_title = st.columns([1, 4])
        try: c_logo.image("logo.png", width=150)
        except: pass
        
        c_title.markdown("## 🔒 Area Riservata - v0.8 Beta")
        
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
VERSION = "v0.8 Beta"
COPYRIGHT = "© Andrea Bossola 2025"

stl_triangles = [] 

# --- UTILITY DATA E ORA ---
def get_timestamp_string():
    return datetime.now().strftime("%Y%m%d_%H%M")

def clean_filename(name):
    return "".join([c if c.isalnum() else "_" for c in name])

# --- 3. NESTING ENGINE ---
class Sheet:
    def __init__(self, w, h, id):
        self.w, self.h = w, h
        self.id = id
        self.items = [] 
        self.used_area = 0
        self.cursor_x = 0
        self.cursor_y = 0
        self.row_h = 0

    def add(self, item):
        margin = 1.0 
        iw, ih = item['w'] + margin, item['h'] + margin
        if self.cursor_x + iw > self.w:
            self.cursor_x = 0
            self.cursor_y += self.row_h
            self.row_h = 0
        if self.cursor_y + ih > self.h: return False
        item['x_pos'] = self.cursor_x
        item['y_pos'] = self.cursor_y
        self.items.append(item)
        self.used_area += item['w'] * item['h']
        self.cursor_x += iw
        self.row_h = max(self.row_h, ih)
        return True

def run_nesting(parts, sheet_w, sheet_h):
    optimized_parts = []
    for p in parts:
        must_rotate = p['h'] > sheet_h
        if must_rotate:
            if p['h'] <= sheet_w: 
                new_w = p['h']
                new_h = p['w']
                new_holes = [(y, x) for x, y in p['holes']]
                p['w'] = new_w
                p['h'] = new_h
                p['holes'] = new_holes
                p['rotated'] = True
            else:
                st.error(f"ATTENZIONE: Il pezzo {p['lbl']} è troppo grande!")
        optimized_parts.append(p)

    parts_sorted = sorted(optimized_parts, key=lambda x: x['h'], reverse=True)
    sheets = []
    current_sheet = Sheet(sheet_w, sheet_h, 1)
    sheets.append(current_sheet)
    
    for p in parts_sorted:
        placed = current_sheet.add(p)
        if not placed:
            current_sheet = Sheet(sheet_w, sheet_h, len(sheets)+1)
            sheets.append(current_sheet)
            current_sheet.add(p)
    return sheets

# --- 4. DXF GENERATOR ---
def generate_dxf(sheets, sheet_w, sheet_h, project_name):
    doc = ezdxf.new()
    msp = doc.modelspace()
    
    doc.layers.new(name='TAGLIO', dxfattribs={'color': 1}) 
    doc.layers.new(name='FORI', dxfattribs={'color': 5})   
    doc.layers.new(name='BORDO_LASTRA', dxfattribs={'color': 7})
    doc.layers.new(name='TESTO', dxfattribs={'color': 3}) 

    offset_x_global = 0 
    date_str = datetime.now().strftime("%d/%m/%Y")

    for sheet in sheets:
        # Bordo
        msp.add_lwpolyline([(offset_x_global,0), (sheet_w+offset_x_global,0), 
                            (sheet_w+offset_x_global,sheet_h), (offset_x_global,sheet_h), 
                            (offset_x_global,0)], dxfattribs={'layer': 'BORDO_LASTRA'})
        
        # Titolo Lastra + Info Progetto
        info_txt = f"LASTRA {sheet.id} | PRJ: {project_name} | {date_str}"
        t = msp.add_text(info_txt, dxfattribs={'layer': 'TESTO', 'height': 4.0})
        t.dxf.insert = (5+offset_x_global, sheet_h - 10)

        for item in sheet.items:
            x0 = item['x_pos'] + offset_x_global
            y0 = item['y_pos']
            
            # Pezzo
            msp.add_lwpolyline([(x0, y0), (x0+item['w'], y0), (x0+item['w'], y0+item['h']), (x0, y0+item['h']), (x0, y0)], 
                               dxfattribs={'layer': 'TAGLIO'})
            
            # Buchi
            for hx, hy in item['holes']:
                cx = x0 + hx
                cy = y0 + hy
                msp.add_circle((cx, cy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
            
            # Label
            lbl_txt = item['lbl'] + (" (R)" if item.get('rotated') else "")
            t_lbl = msp.add_text(lbl_txt, dxfattribs={'layer': 'TESTO', 'height': 2.5})
            t_lbl.dxf.insert = (x0 + 2, y0 + 2)
            
        offset_x_global += sheet_w + 20 

    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

# --- 5. LOGICA CARICAMENTO ---
def load_config(f):
    try:
        data = json.load(f)
        st.session_state['project_name'] = data.get('project_name', 'Progetto')
        st.session_state['num_colonne'] = data.get('num_colonne', 1)
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
    # --- LOGO ---
    try: st.image("logo.png", width=200) 
    except: st.markdown("## MOBY")
    
    st.caption(f"User: {st.session_state.username} | {VERSION}")
    
    st.divider()
    
    # --- INPUT NOME PROGETTO ---
    if 'project_name' not in st.session_state: st.session_state['project_name'] = "Nuovo_Progetto"
    proj_name_input = st.text_input("Nome Progetto", value=st.session_state['project_name'])
    st.session_state['project_name'] = clean_filename(proj_name_input)
    
    st.divider()
    
    f = st.file_uploader("Carica JSON", type=["json"])
    if f: load_config(f)
    
    st.divider()
    st.header("📐 Configurazione")
    num_colonne = st.number_input("Moduli", 1, 10, 2, key="num_colonne")
    
    dati_colonne = []
    lista_pezzi_ferro = [] 

    for i in range(num_colonne):
        with st.expander(f"Modulo {i+1}", expanded=False):
            c1, c2 = st.columns(2)
            w = c1.number_input("L", 30, 200, 60, key=f"w_{i}")
            d = c2.number_input("P", 20, 100, 30, key=f"d_{i}")
            c3, c4 = st.columns(2)
            h = c3.number_input("H", 50, 400, 200, key=f"h_{i}")
            r = c4.number_input("Ripiani", 1, 20, 4, key=f"r_{i}")
            
            is_manual = st.checkbox("Libera", key=f"man_{i}")
            mh = []
            
            z_shelves = []
            if is_manual:
                step = (h - SPESSORE_LEGNO)/(r-1) if r>1 else 0
                for k in range(r):
                    def_val = int(k*step)
                    if k == r-1 and r > 1: def_val = int(h - SPESSORE_LEGNO)
                    val = st.number_input(f"M {k+1}", value=def_val, key=f"h_shelf_{i}_{k}")
                    mh.append(val)
                z_shelves = [float(x) for x in mh]
            else:
                if r == 1: z_shelves = [0.0]
                else:
                    step = (h - SPESSORE_LEGNO)/(r-1)
                    z_shelves = [n*step for n in range(r)]
            
            dati_colonne.append({"w":w, "h":h, "d":d, "r":r, "man":is_manual, "mh":z_shelves})

            # CALCOLO POSIZIONE FORI
            holes_coords = []
            for z in z_shelves:
                center_y = z + (SPESSORE_LEGNO / 2.0) 
                holes_coords.append((OFFSET_LATERALI, center_y)) 
                holes_coords.append((d / 2.0, center_y))         
                holes_coords.append((d - OFFSET_LATERALI, center_y)) 
            
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M{i+1}_SX", "holes": holes_coords, "rotated": False})
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M{i+1}_DX", "holes": holes_coords, "rotated": False})

    st.markdown("---")
    st.markdown(f"**{COPYRIGHT}**")


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

for i, dc in enumerate(dati_colonne):
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro SX M{i+1}"))
    cx += SPESSORE_FERRO
    for idx, z in enumerate(dc["mh"]):
        fig.add_trace(draw(cx, 0, z, dc["w"], dc["d"], SPESSORE_LEGNO, C_WOOD, f"Piano {idx+1}"))
    cx += dc["w"]
    fig.add_trace(draw(cx, 0, 0, SPESSORE_FERRO, dc["d"], dc["h"], C_IRON, f"Ferro DX M{i+1}"))
    cx += SPESSORE_FERRO

def get_bin_stl(tris):
    out = io.BytesIO()
    out.write(b'\0'*80 + struct.pack('<I', len(tris)))
    for p in tris: out.write(struct.pack('<ffffffffffffH', 0,0,0, *p[0], *p[1], *p[2], 0))
    return out.getvalue()

# NOMI FILE CON TIMESTAMP
ts = get_timestamp_string()
prj = st.session_state['project_name']
fname_json = f"{prj}_{ts}.json"
fname_stl = f"{prj}_{ts}.stl"
fname_dxf = f"{prj}_{ts}_Taglio.dxf"

proj_data = {"project_name": prj, "num_colonne":st.session_state['num_colonne'], "cols":dati_colonne}

with st.sidebar:
    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj_data), fname_json, "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), fname_stl, "application/octet-stream")

# --- 8. UI TABELLARE ---
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
        if n_sheets > 0:
             waste_pct = ((n_sheets*sheet_w*sheet_h - sum([s.used_area for s in sheets_result])) / (n_sheets*sheet_w*sheet_h)) * 100
        else: waste_pct = 0
        
        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("Lastre", n_sheets)
        c_res2.metric("Costo Materiale", f"€ {tot_cost:.2f}")
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
                    cx = item['x_pos'] + hx
                    cy = item['y_pos'] + hy
                    shapes.append(dict(
                        type="circle",
                        xref="x", yref="y",
                        x0=cx - 1, y0=cy - 1, 
                        x1=cx + 1, y1=cy + 1,
                        line_color="blue", fillcolor="blue"
                    ))

            fig_2d = go.Figure()
            fig_2d.update_layout(shapes=shapes, annotations=annotations, xaxis=dict(range=[-10, sheet_w+10], showgrid=True), yaxis=dict(range=[-10, sheet_h+10], scaleanchor="x"), height=500, margin=dict(l=10, r=10, t=10, b=10))
            
            st.plotly_chart(fig_2d, width="stretch", key=f"sheet_preview_{s.id}")
            
            # DOWNLOAD SINGOLA LASTRA
            fname_lastra = f"{prj}_{ts}_Lastra{s.id}.dxf"
            dxf_single = generate_dxf([s], sheet_w, sheet_h, prj)
            st.download_button(f"💾 DXF Lastra {s.id}", dxf_single, fname_lastra, "application/dxf", key=f"btn_{s.id}")
            
        st.divider()
        # DOWNLOAD COMPLETO
        dxf_full = generate_dxf(sheets_result, sheet_w, sheet_h, prj)
        st.download_button("📦 SCARICA TUTTO (Tutte le Lastre)", dxf_full, fname_dxf, "application/dxf", type="primary")
