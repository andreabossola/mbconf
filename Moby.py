
import streamlit as st
import plotly.graph_objects as go
import struct
import io
import json
import ezdxf 

# --- 1. SETUP & LOGIN ---
st.set_page_config(layout="wide", page_title="Moby Esecutivi")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if not st.session_state.logged_in:
        st.markdown("## 🔒 Moby Esecutivi")
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
            else: st.error("Errore")
        st.stop()

check_login()

# --- 2. COSTANTI ---
SPESSORE_LEGNO = 4.0  
SPESSORE_FERRO = 0.3  
DIAMETRO_FORO = 0.6 
OFFSET_LATERALI = 3.0 
stl_triangles = [] 

# --- 3. FUNZIONE GENERA DXF SINGOLO PEZZO ---
def generate_part_dxf(part, rotate_horizontal=True):
    # part: {'w': profondita, 'h': altezza, 'holes': [(x,y)], 'lbl': nome}
    doc = ezdxf.new()
    msp = doc.modelspace()
    
    # Layers
    doc.layers.new(name='TAGLIO', dxfattribs={'color': 1}) # Rosso
    doc.layers.new(name='FORI', dxfattribs={'color': 5})   # Blu
    doc.layers.new(name='TESTO', dxfattribs={'color': 3}) 

    # Dimensioni
    if rotate_horizontal:
        # Ruotiamo: X diventa Altezza Colonna, Y diventa Profondità
        dim_x = part['h']
        dim_y = part['w']
    else:
        dim_x = part['w']
        dim_y = part['h']

    # 1. Rettangolo Esterno (TAGLIO)
    msp.add_lwpolyline([(0,0), (dim_x,0), (dim_x,dim_y), (0,dim_y), (0,0)], 
                       dxfattribs={'layer': 'TAGLIO'})
    
    # 2. Buchi (FORI)
    for hx, hy in part['holes']:
        # hx era sulla profondità (w), hy era sull'altezza (h)
        # Se ruotiamo: nuova_x = hy, nuova_y = hx
        if rotate_horizontal:
            cx = hy
            cy = hx # Attenzione: hx in input era la coordinata sulla profondità
        else:
            cx = hx
            cy = hy
            
        msp.add_circle((cx, cy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
    
    # 3. Etichetta
    t = msp.add_text(part['lbl'], dxfattribs={'layer': 'TESTO', 'height': 2.5})
    t.dxf.insert = (2, 2)

    out = io.StringIO()
    doc.write(out)
    return out.getvalue()

# --- 4. FUNZIONE DXF UNICO (TUTTI I PEZZI IN FILA) ---
def generate_all_parts_dxf(parts_list):
    doc = ezdxf.new()
    msp = doc.modelspace()
    
    doc.layers.new(name='TAGLIO', dxfattribs={'color': 1}) 
    doc.layers.new(name='FORI', dxfattribs={'color': 5})   
    doc.layers.new(name='TESTO', dxfattribs={'color': 3}) 

    cursor_x = 0
    gap = 10 # cm tra un pezzo e l'altro

    for part in parts_list:
        # Ruotiamo sempre in orizzontale per comodità
        dim_x = part['h']
        dim_y = part['w']

        # Rettangolo
        msp.add_lwpolyline([(cursor_x,0), (cursor_x+dim_x,0), (cursor_x+dim_x,dim_y), (cursor_x,dim_y), (cursor_x,0)], 
                           dxfattribs={'layer': 'TAGLIO'})
        
        # Buchi
        for hx, hy in part['holes']:
            cx = cursor_x + hy # hy diventa X (lunghezza)
            cy = hx            # hx diventa Y (profondità)
            msp.add_circle((cx, cy), radius=DIAMETRO_FORO/2, dxfattribs={'layer': 'FORI'})
        
        # Testo
        t = msp.add_text(part['lbl'], dxfattribs={'layer': 'TESTO', 'height': 5.0})
        t.dxf.insert = (cursor_x + 2, dim_y + 2)

        cursor_x += dim_x + gap

    out = io.StringIO()
    doc.write(out)
    return out.getvalue()


# --- 5. LOGICA CARICAMENTO ---
def load_config(f):
    try:
        data = json.load(f)
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
    st.header(f"User: {st.session_state.username}")
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
            # Coordinate: X = Lungo la profondità (0 -> d), Y = Lungo l'altezza (0 -> h)
            holes_coords = []
            for z in z_shelves:
                center_y = z + (SPESSORE_LEGNO / 2.0) 
                holes_coords.append((OFFSET_LATERALI, center_y)) # Fronte
                holes_coords.append((d / 2.0, center_y))         # Centro
                holes_coords.append((d - OFFSET_LATERALI, center_y)) # Retro
            
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M{i+1}_SX", "holes": holes_coords})
            lista_pezzi_ferro.append({"w": d, "h": h, "lbl": f"M{i+1}_DX", "holes": holes_coords})


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

proj = {"num_colonne":st.session_state['num_colonne'], "cols":dati_colonne}

with st.sidebar:
    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button("💾 JSON", json.dumps(proj), "moby.json", "application/json")
    c2.download_button("🧊 STL", get_bin_stl(stl_triangles), "moby.stl", "application/octet-stream")

# --- 8. UI TABELLARE ---
tab1, tab2 = st.tabs(["🎥 3D Config", "🏭 FILES TAGLIO (Esecutivi)"])

with tab1:
    fig.update_layout(scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(title="H"), aspectmode='data', bgcolor="white"), margin=dict(t=0,b=0,l=0,r=0), height=600)
    st.plotly_chart(fig, width="stretch")

with tab2:
    st.markdown("### Esecutivi Produzione (Ferro)")
    st.info("Qui trovi i file DXF per ogni singolo pezzo, già forati e ruotati in orizzontale per il taglio.")
    
    if len(lista_pezzi_ferro) > 0:
        
        # BOTTONE GLOBAL
        dxf_all = generate_all_parts_dxf(lista_pezzi_ferro)
        st.download_button(
            label="📥 SCARICA TUTTI I PEZZI (Unico DXF)",
            data=dxf_all,
            file_name="tutti_i_pezzi_moby.dxf",
            mime="application/dxf",
            type="primary"
        )
        
        st.divider()
        
        # LISTA PEZZI SINGOLI
        for idx, part in enumerate(lista_pezzi_ferro):
            c_prev, c_btn = st.columns([3, 1])
            
            # Anteprima 2D
            # X=Altezza, Y=Profondità (Ruotato)
            dim_x = part['h']
            dim_y = part['w']
            
            shapes = [
                dict(type="rect", x0=0, y0=0, x1=dim_x, y1=dim_y, line=dict(color="red"), fillcolor="rgba(255,0,0,0.1)")
            ]
            
            for hx, hy in part['holes']:
                # Nel plot 2D simuliamo la rotazione: X=hy, Y=hx
                cx = hy
                cy = hx
                shapes.append(dict(type="circle", x0=cx-1, y0=cy-1, x1=cx+1, y1=cy+1, line_color="blue", fillcolor="blue"))
            
            fig_2d = go.Figure()
            fig_2d.update_layout(
                title=f"{part['lbl']} ({dim_x} x {dim_y} cm)",
                shapes=shapes, 
                xaxis=dict(range=[-5, dim_x+5], title="Lunghezza (ex Altezza)", showgrid=True), 
                yaxis=dict(range=[-5, dim_y+5], title="Larghezza (ex Prof)", scaleanchor="x"), 
                height=150, margin=dict(l=10, r=10, t=30, b=10)
            )
            
            with c_prev:
                st.plotly_chart(fig_2d, width="stretch", key=f"prev_{idx}")
            
            with c_btn:
                st.write("##") # Spacer
                dxf_single = generate_part_dxf(part)
                st.download_button(
                    label="⬇️ DXF",
                    data=dxf_single,
                    file_name=f"{part['lbl']}.dxf",
                    mime="application/dxf",
                    key=f"btn_{idx}"
                )
                st.caption(f"{len(part['holes'])} fori")
            
            st.divider()