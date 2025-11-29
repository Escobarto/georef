
import streamlit as st
from pathlib import Path
import pandas as pd
import json
import time
import difflib
from io import BytesIO
from PIL import Image

BASE = Path(__file__).resolve().parent
DATA_CSV = BASE / "sample_acervo.csv"
DB_JSON = BASE / "acervo_db.json"
LOGS_JSON = BASE / "usage_logs.json"
FOLKSONOMY_FORM_URL = "https://forms.gle/qRqWxzCPYDDVNDp36"  # example link (replace with your form)

st.set_page_config(page_title="Sistema de Documentação - NUGEP", layout="wide")

# --- Utilities ---
def load_acervo():
    if DB_JSON.exists():
        try:
            return pd.read_json(DB_JSON, orient="records")
        except Exception:
            pass
    return pd.read_csv(DATA_CSV)

def save_acervo(df):
    df.to_json(DB_JSON, orient="records", force_ascii=False, indent=2)

def log_event(event):
    entry = {"timestamp": time.time(), "event": event}
    logs = []
    if LOGS_JSON.exists():
        try:
            logs = json.loads(LOGS_JSON.read_text(encoding='utf-8'))
        except Exception:
            logs = []
    logs.append(entry)
    LOGS_JSON.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding='utf-8')

# Load or initialize
acervo_df = load_acervo()

# Sidebar
st.sidebar.title("NUGEP - Sistema de Documentação")
menu = st.sidebar.radio("Navegação", ["Dashboard", "Criar Ficha", "Mapa Interativo", "Galeria", "Chatbot", "Exportar / Importar", "Sobre"])

# --- Dashboard ---
if menu == "Dashboard":
    st.header("Dashboard do Acervo")
    st.markdown("Resumo rápido das coleções carregadas.")
    st.metric("Itens no acervo", len(acervo_df))
    st.dataframe(acervo_df[["id","titulo","autor","ano","categoria","tags"]])
    # Show tags distribution
    st.subheader("Distribuição de categorias")
    cat_counts = acervo_df["categoria"].value_counts().rename_axis("categoria").reset_index(name="count")
    st.bar_chart(cat_counts.set_index("categoria")["count"])
    st.subheader("Últimos registros (mostrando campos principais)")
    st.table(acervo_df.tail(5)[["id","titulo","autor","ano","categoria"]])
    log_event({"action":"view_dashboard","items":len(acervo_df)})

# --- Criar Ficha ---
elif menu == "Criar Ficha":
    st.header("Criar nova ficha de objeto")
    with st.form("form_ficha", clear_on_submit=True):
        titulo = st.text_input("Título")
        autor = st.text_input("Autor / Comunidade")
        ano = st.text_input("Ano (ou período)")
        categoria = st.text_input("Categoria")
        descricao = st.text_area("Descrição (contexto, uso, procedência)")
        col1, col2 = st.columns(2)
    with col1:
        endereco = st.text_input("Localização / Endereço (ex: Rua, Bairro, Cidade)")
    with col2:
        tags = st.text_input("Tags (separadas por ; )")
        imagem = st.file_uploader(
            "Imagem do objeto (opcional)",
            type=["png", "jpg", "jpeg"]
        )

        submitted = st.form_submit_button("Salvar ficha")
        if submitted:
            new_id = str(int(acervo_df["id"].max())+1) if not acervo_df.empty else "1"
            image_path = ""
            if imagem:
                img = Image.open(imagem)
                img_path = BASE / "uploads"
                img_path.mkdir(exist_ok=True)
                
                # força sempre salvar como PNG, independentemente da extensão
                save_path = img_path / f"obj_{new_id}.png"
                img.save(save_path)
                image_path = str(save_path.relative_to(BASE))

                # força a extensão para minúsculo
                ext = Path(imagem.name).suffix.lower()
                if ext not in [".png", ".jpg", ".jpeg"]:
                    ext = ".png"  # fallback seguro

                save_path = img_path / f"obj_{new_id}{ext}"
                img.save(save_path)
                image_path = str(save_path.relative_to(BASE))

            new_row = {
            "id": new_id,
            "titulo": titulo,
            "autor": autor,
            "ano": ano,
            "categoria": categoria,
            "endereco": endereco,
            "descricao": descricao,
            "imagem": image_path,
            "tags": tags
        }

            acervo_df = pd.concat([acervo_df, pd.DataFrame([new_row])], ignore_index=True)
            save_acervo(acervo_df)
            st.success("Ficha salva com sucesso!")
            log_event({"action": "create_record", "id": new_id, "titulo": titulo})

# --- Mapa Interativo ---
elif menu == "Mapa Interativo":
    st.header("🗺️ Mapa interativo do acervo")
    st.markdown("Visualize os objetos do acervo georreferenciados.")

    try:
        import folium
        from streamlit_folium import st_folium
    except Exception:
        st.error("Instale as dependências: pip install folium streamlit-folium")
        st.stop()

    # Verifica se há colunas de coordenadas
    if "latitude" not in acervo_df.columns or "longitude" not in acervo_df.columns:
        st.warning("⚠️ O arquivo não contém colunas 'latitude' e 'longitude'. Adicione-as para gerar o mapa.")
        st.stop()

    # Converte e limpa as coordenadas
    acervo_df["latitude"] = pd.to_numeric(acervo_df["latitude"], errors="coerce")
    acervo_df["longitude"] = pd.to_numeric(acervo_df["longitude"], errors="coerce")
    valid_df = acervo_df.dropna(subset=["latitude", "longitude"])

    if valid_df.empty:
        st.warning("⚠️ Nenhum dado válido de latitude/longitude encontrado.")
        st.write("Prévia dos dados brutos:", acervo_df[["titulo", "latitude", "longitude"]].head())
        st.stop()

    # Centraliza o mapa
    lat_media = valid_df["latitude"].mean()
    lon_media = valid_df["longitude"].mean()

    m = folium.Map(location=[lat_media, lon_media], zoom_start=5)

    # Adiciona marcadores
    for _, row in valid_df.iterrows():
        folium.Marker(
            [row["latitude"], row["longitude"]],
            popup=f"<b>{row['titulo']}</b><br>{row['categoria']} - {row['autor']}"
        ).add_to(m)

    st_folium(m, width=900, height=600)
    log_event({"action": "view_map", "count": len(valid_df)})


# --- Galeria ---
elif menu == "Galeria":
    st.header("Galeria de Objetos")
    st.markdown("Clique em uma imagem para abrir a ficha completa.")
    cols = st.columns(3)
    for idx, row in acervo_df.iterrows():
        col = cols[idx % 3]
        img_path = BASE / row["imagem"] if row["imagem"] else BASE / "sample_images" / f"objeto_{(idx%5)+1}.png"
        try:
            img = Image.open(img_path)
            col.image(img, caption=f"{row['titulo']} ({row['ano']})", use_container_width=True)
            if col.button(f"Ver ficha {row['id']}", key=f"btn_{row['id']}"):
                st.subheader(f"Ficha: {row['titulo']}")
                st.write("**Autor / Comunidade:**", row["autor"])
                st.write("**Ano / Período:**", row["ano"])
                st.write("**Categoria:**", row["categoria"])
                st.write("**Descrição:**", row["descricao"])
                st.write("**Tags:**", row["tags"])
                if row["imagem"]:
                    try:
                        st.image(Image.open(BASE / row["imagem"]), use_container_width=True)
                    except Exception:
                        pass
                log_event({"action": "view_record", "id": row["id"]})
        except Exception as e:
            continue

# --- Chatbot ---
elif menu == "Chatbot":
    st.header("Chatbot NUGEP - Auxílio à consulta do acervo")
    st.markdown("Faça uma pergunta sobre as obras cadastradas. O chatbot busca correspondências exatas e por similaridade.")
    pergunta = st.text_input("Pergunte sobre o acervo:")
    if st.button("Enviar"):
        if not pergunta:
            st.warning("Digite uma pergunta antes de enviar.")
        else:
            # Simple matching: exact keys in titles, tags, description, and fuzzy match on titles
            q = pergunta.lower().strip()
            
            # Exact title match
            matches = acervo_df[acervo_df["titulo"].str.lower() == q]
            if not matches.empty:
                row = matches.iloc[0]
                st.markdown(f"**Resposta (exata):** {row['titulo']} - {row['descricao']}")
                log_event({"action": "chat_exact", "query": pergunta, "id": row["id"]})
            else:
                # Fuzzy match on title
                titles = acervo_df["titulo"].astype(str).str.lower().tolist()
                close = difflib.get_close_matches(q, titles, n=1, cutoff=0.6)
                if close:
                    row = acervo_df[acervo_df["titulo"].str.lower() == close[0]].iloc[0]
                    st.markdown(f"**Acredito que você quis dizer:** {row['titulo']}\n\n{row['descricao']}")
                    log_event({"action": "chat_fuzzy", "query": pergunta, "id": row["id"]})
                else:
                    # Search in description and tags
                    mask = acervo_df["descricao"].str.lower().str.contains(q) | acervo_df["tags"].str.lower().str.contains(q)
                    if mask.any():
                        row = acervo_df[mask].iloc[0]
                        st.markdown(f"**Encontrado por conteúdo:** {row['titulo']} - {row['descricao']}")
                        log_event({"action": "chat_search", "query": pergunta, "id": row["id"]})
                    else:
                        st.info("Desculpe, não encontrei informações específicas sobre sua pergunta. Tente outra palavra-chave.")
                        st.markdown(f"Contribua com novas tags e termos através do formulário de folksonomia: [Adicionar tags]({FOLKSONOMY_FORM_URL})")
                        log_event({"action": "chat_no_match", "query": pergunta})
