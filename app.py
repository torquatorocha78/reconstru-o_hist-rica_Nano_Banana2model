
import io
import os
import time
from pathlib import Path

import streamlit as st
from PIL import Image
from google import genai
from google.genai import types


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Reconstrução Histórica com IA",
    page_icon="📷",
    layout="wide",
)


# ============================================================
# MODELOS
# ============================================================

IMAGE_MODELS = {
    "Nano Banana 2 — recomendado": "gemini-3.1-flash-image",
    "Nano Banana Pro — maior controle": "gemini-3-pro-image",
    "Nano Banana — legado": "gemini-2.5-flash-image",
}

VIDEO_MODEL = "veo-3.1-generate-preview"


# ============================================================
# API
# ============================================================

def get_api_key():
    try:
        key = st.secrets.get("GOOGLE_API_KEY", "")
    except Exception:
        key = ""

    if not key:
        key = os.environ.get("GOOGLE_API_KEY", "")

    return key.strip()


def make_client():
    key = get_api_key()

    if not key:
        return None

    return genai.Client(api_key=key)


# ============================================================
# IMAGENS
# ============================================================

def uploaded_to_pil(uploaded_file):
    if uploaded_file is None:
        return None

    return Image.open(
        io.BytesIO(uploaded_file.getvalue())
    ).convert("RGB")


def image_part(uploaded_file):
    """
    Converte upload Streamlit em Part compatível com Gemini.
    """

    if uploaded_file is None:
        return None

    return types.Part.from_bytes(
        data=uploaded_file.getvalue(),
        mime_type=uploaded_file.type or "image/jpeg",
    )


# ============================================================
# GERAÇÃO DA FOTOGRAFIA
# ============================================================

def generate_image(
    client,
    prompt,
    uploads,
    model,
    aspect_ratio,
    resolution,
):
    contents = [prompt]

    for upload in uploads:
        part = image_part(upload)

        if part is not None:
            contents.append(part)

    # --------------------------------------------------------
    # CONFIGURAÇÃO DO GEMINI
    # --------------------------------------------------------

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=resolution,
        ),
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    generated = None
    explanation = []

    # --------------------------------------------------------
    # PROCESSA A RESPOSTA
    # --------------------------------------------------------

    for part in response.parts:

        if getattr(part, "text", None):
            explanation.append(part.text)

        elif getattr(part, "inline_data", None):

            try:
                generated = part.as_image()

            except Exception as exc:
                raise RuntimeError(
                    "A API retornou dados de imagem, "
                    "mas o SDK não conseguiu convertê-los: "
                    f"{exc}"
                )

    if generated is None:
        raise RuntimeError(
            "A API respondeu, mas não retornou uma imagem. "
            "Tente reduzir o número de referências, "
            "alterar o modelo ou reduzir a resolução."
        )

    return generated, "\n".join(explanation)


# ============================================================
# GERAÇÃO DO VÍDEO
# ============================================================

def generate_video(
    client,
    prompt,
    main_image_upload,
    reference_uploads,
    resolution,
    aspect_ratio,
):

    # --------------------------------------------------------
    # IMAGEM PRINCIPAL
    # --------------------------------------------------------

    first_image = None

    if main_image_upload is not None:

        first_image = types.Image.from_bytes(
            data=main_image_upload.getvalue(),
            mime_type=main_image_upload.type or "image/jpeg",
        )

    # --------------------------------------------------------
    # REFERÊNCIAS
    # --------------------------------------------------------

    refs = []

    for upload in reference_uploads[:3]:

        if upload is None:
            continue

        refs.append(
            types.VideoGenerationReferenceImage(
                image=types.Image.from_bytes(
                    data=upload.getvalue(),
                    mime_type=upload.type or "image/jpeg",
                ),
                reference_type="asset",
            )
        )

    # --------------------------------------------------------
    # CONFIGURAÇÃO VEO
    # --------------------------------------------------------

    config = types.GenerateVideosConfig(
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        number_of_videos=1,
        reference_images=refs if refs else None,
    )

    # --------------------------------------------------------
    # INICIA GERAÇÃO
    # --------------------------------------------------------

    operation = client.models.generate_videos(
        model=VIDEO_MODEL,
        prompt=prompt,
        image=first_image,
        config=config,
    )

    progress = st.progress(
        0,
        text="Enviando o trabalho para o Veo…",
    )

    checks = 0

    # --------------------------------------------------------
    # AGUARDA
    # --------------------------------------------------------

    while not operation.done:

        checks += 1

        progress.progress(
            min(95, 10 + checks * 5),
            text="Gerando vídeo… aguarde.",
        )

        time.sleep(10)

        operation = client.operations.get(operation)

    progress.progress(
        100,
        text="Vídeo concluído.",
    )

    # --------------------------------------------------------
    # VERIFICA RESULTADO
    # --------------------------------------------------------

    if (
        not operation.response
        or not operation.response.generated_videos
    ):
        raise RuntimeError(
            "O Veo terminou sem retornar um vídeo."
        )

    generated_video = (
        operation.response
        .generated_videos[0]
        .video
    )

    # --------------------------------------------------------
    # TENTA OBTER BYTES DIRETAMENTE
    # --------------------------------------------------------

    try:

        if getattr(
            generated_video,
            "video_bytes",
            None,
        ):
            return generated_video.video_bytes

    except Exception:
        pass

    # --------------------------------------------------------
    # DOWNLOAD DO ARQUIVO
    # --------------------------------------------------------

    out = io.BytesIO()

    try:

        client.files.download(
            file=generated_video,
            destination=out,
        )

        return out.getvalue()

    except Exception:

        temp = Path("video_result.mp4")

        client.files.download(
            file=generated_video,
            destination=str(temp),
        )

        data = temp.read_bytes()

        try:
            temp.unlink()
        except Exception:
            pass

        return data


# ============================================================
# PROMPT PADRÃO — FOTOGRAFIA
# ============================================================

def default_reconstruction_prompt():

    return """Reconstrua/restaure esta fotografia histórica mantendo o máximo de fidelidade documental.

OBJETIVO:

- preservar a identidade e aparência das pessoas da foto de referência;
- preservar arquitetura, posição das construções, portas, janelas, cercas, postes, veículos, estrada e relevo;
- recuperar detalhes perdidos por desbotamento, baixa resolução, manchas e ruído;
- reconstruir apenas o que estiver plausivelmente indicado pelas fotografias e referências fornecidas;
- não inventar uma arquitetura moderna ou substituir a construção histórica por outra;
- manter a perspectiva e o enquadramento da fotografia principal;
- aparência fotográfica histórica realista, não ilustração e não pintura.

QUANDO HOUVER MAIS DE UMA REFERÊNCIA:

A primeira imagem é a fotografia principal.

As demais são referências documentais.

Use as referências para resolver detalhes de pessoas, casa, paisagem, veículo e composição.

Não copie elementos que contradigam a fotografia principal.

FIDELIDADE HISTÓRICA:

- não modernizar roupas;
- não modernizar veículos;
- não modernizar arquitetura;
- não adicionar postes, fios, placas, prédios ou objetos contemporâneos;
- preservar proporções;
- preservar posição relativa dos elementos;
- preservar características faciais;
- preservar características arquitetônicas;
- preservar o ambiente natural da época.

RESTAURAÇÃO:

- remover manchas;
- reduzir riscos;
- recuperar contraste;
- recuperar detalhes;
- melhorar nitidez de forma natural;
- corrigir desbotamento;
- preservar textura fotográfica;
- evitar aparência artificial de imagem gerada por IA.

RESULTADO:

Uma fotografia historicamente plausível, natural, com textura fotográfica e iluminação coerente com a época.

Não adicionar texto, letreiros, marcas d'água ou elementos contemporâneos."""


# ============================================================
# PROMPT PADRÃO — VÍDEO
# ============================================================

def default_video_prompt():

    return """Anime esta reconstrução histórica de maneira extremamente natural e documental.

Preserve a identidade das pessoas, a arquitetura, a paisagem, a posição dos objetos e a aparência da época.

Movimento de câmera muito lento e discreto, como uma filmagem documental antiga.

Movimentos humanos mínimos e plausíveis.

Nada de deformar rostos, mãos, roupas, casas ou veículos.

Não modernizar o cenário.

Não inserir pessoas, prédios, carros, placas ou objetos que não estejam nas referências.

A fotografia histórica restaurada deve ganhar vida com movimento realista e cinematográfico extremamente sutil."""


# ============================================================
# INTERFACE
# ============================================================

st.title("📷 Reconstrução Histórica com IA")

st.caption(
    "Fotografias antigas → reconstrução/restauração → "
    "vídeo histórico com movimento"
)


# ============================================================
# API KEY
# ============================================================

api_key = get_api_key()

if not api_key:

    st.warning(
        "A API key do Google Gemini ainda não foi configurada. "
        "Veja o passo a passo na aba **⚙️ Configuração da API**."
    )


# ============================================================
# ABAS
# ============================================================

tab_img, tab_video, tab_config = st.tabs(
    [
        "🖼️ Reconstruir fotografia",
        "🎬 Gerar vídeo",
        "⚙️ Configuração da API",
    ]
)


# ============================================================
# ABA — FOTOGRAFIA
# ============================================================

with tab_img:

    st.subheader("1. Envie as referências")

    st.write(
        "Use a primeira imagem como fotografia principal. "
        "As outras podem ser fotos da mesma casa, pessoa, "
        "paisagem, veículo ou um desenho/esboço."
    )

    main_photo = st.file_uploader(
        "Fotografia histórica principal",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="main_photo",
    )

    c1, c2 = st.columns(2)

    with c1:

        person_ref = st.file_uploader(
            "Referência da pessoa / família (opcional)",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="person_ref",
        )

        house_ref = st.file_uploader(
            "Referência da casa / arquitetura (opcional)",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="house_ref",
        )

    with c2:

        landscape_ref = st.file_uploader(
            "Referência da paisagem / praia / rua (opcional)",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="landscape_ref",
        )

        sketch_ref = st.file_uploader(
            "Desenho / croqui de posição (opcional)",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="sketch_ref",
        )

    extra_ref = st.file_uploader(
        "Outra referência (opcional)",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="extra_ref",
    )

    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    st.subheader(
        "2. Defina como a reconstrução deve ser feita"
    )

    prompt = st.text_area(
        "Prompt",
        value=default_reconstruction_prompt(),
        height=380,
        key="image_prompt",
    )

    # --------------------------------------------------------
    # CONFIGURAÇÕES
    # --------------------------------------------------------

    c1, c2, c3 = st.columns(3)

    with c1:

        model_label = st.selectbox(
            "Modelo",
            list(IMAGE_MODELS.keys()),
        )

    with c2:

        aspect_ratio = st.selectbox(
            "Proporção",
            [
                "16:9",
                "4:3",
                "3:2",
                "1:1",
                "3:4",
                "9:16",
            ],
            index=0,
        )

    with c3:

        resolution = st.selectbox(
            "Resolução",
            [
                "1K",
                "2K",
                "4K",
            ],
            index=1,
        )

    # --------------------------------------------------------
    # PRÉVIA
    # --------------------------------------------------------

    if main_photo:

        st.image(
            main_photo,
            caption="Fotografia principal",
            use_container_width=True,
        )

    # --------------------------------------------------------
    # BOTÃO
    # --------------------------------------------------------

    if st.button(
        "✨ RECONSTRUIR FOTOGRAFIA",
        type="primary",
        use_container_width=True,
        disabled=not bool(
            api_key and main_photo
        ),
    ):

        client = make_client()

        refs = [
            main_photo,
            person_ref,
            house_ref,
            landscape_ref,
            sketch_ref,
            extra_ref,
        ]

        refs = [
            x for x in refs
            if x is not None
        ]

        with st.spinner(
            "A IA está reconstruindo a fotografia…"
        ):

            try:

                image, explanation = generate_image(
                    client=client,
                    prompt=prompt,
                    uploads=refs,
                    model=IMAGE_MODELS[model_label],
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )

                st.session_state[
                    "last_image"
                ] = image

                st.session_state[
                    "last_image_bytes"
                ] = None

                st.session_state[
                    "last_image_prompt"
                ] = prompt

                st.success(
                    "Reconstrução concluída."
                )

                st.image(
                    image,
                    caption="Resultado",
                    use_container_width=True,
                )

                if explanation:

                    with st.expander(
                        "Observação retornada pelo modelo"
                    ):
                        st.write(explanation)

            except Exception as exc:

                st.error(
                    f"Erro ao gerar a fotografia: {exc}"
                )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    if "last_image" in st.session_state:

        st.divider()

        st.subheader(
            "Resultado atual"
        )

        st.image(
            st.session_state["last_image"],
            use_container_width=True,
        )

        buf = io.BytesIO()

        st.session_state[
            "last_image"
        ].save(
            buf,
            format="PNG",
        )

        st.download_button(
            "⬇️ Baixar fotografia reconstruída",
            data=buf.getvalue(),
            file_name="fotografia_reconstruida.png",
            mime="image/png",
            use_container_width=True,
        )


# ============================================================
# ABA — VÍDEO
# ============================================================

with tab_video:

    st.subheader(
        "Transforme a fotografia em um pequeno filme histórico"
    )

    st.info(
        "O Veo 3.1 gera vídeos curtos. "
        "Para uma reconstrução mais consistente, "
        "use a imagem reconstruída como imagem principal "
        "e até 3 referências."
    )

    generated_img = st.session_state.get(
        "last_image"
    )

    if generated_img is not None:

        st.image(
            generated_img,
            caption="Fotografia reconstruída disponível",
            width=500,
        )

    video_start = st.file_uploader(
        "Imagem inicial do vídeo "
        "(se deixar vazio, use a reconstrução acima)",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="video_start",
    )

    v1, v2, v3 = st.columns(3)

    with v1:

        video_ref1 = st.file_uploader(
            "Referência de vídeo 1",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="video_ref1",
        )

    with v2:

        video_ref2 = st.file_uploader(
            "Referência de vídeo 2",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="video_ref2",
        )

    with v3:

        video_ref3 = st.file_uploader(
            "Referência de vídeo 3",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="video_ref3",
        )

    video_prompt = st.text_area(
        "Prompt do vídeo",
        value=default_video_prompt(),
        height=300,
        key="video_prompt",
    )

    vc1, vc2 = st.columns(2)

    with vc1:

        video_resolution = st.selectbox(
            "Resolução do vídeo",
            [
                "720p",
                "1080p",
                "4k",
            ],
            index=0,
        )

    with vc2:

        video_ratio = st.selectbox(
            "Proporção do vídeo",
            [
                "16:9",
                "9:16",
            ],
            index=0,
        )

    start_available = bool(
        video_start or generated_img
    )

    if st.button(
        "🎬 GERAR VÍDEO COM VEO 3.1",
        type="primary",
        use_container_width=True,
        disabled=not bool(
            api_key and start_available
        ),
    ):

        client = make_client()

        if video_start is None:

            temp = io.BytesIO()

            generated_img.save(
                temp,
                format="PNG",
            )

            class MemoryUpload:

                type = "image/png"

                def getvalue(self):
                    return temp.getvalue()

            video_start = MemoryUpload()

        refs = [
            video_ref1,
            video_ref2,
            video_ref3,
        ]

        refs = [
            x for x in refs
            if x is not None
        ]

        with st.spinner(
            "Gerando o vídeo no Veo 3.1. "
            "Isso pode levar alguns minutos…"
        ):

            try:

                video_bytes = generate_video(
                    client=client,
                    prompt=video_prompt,
                    main_image_upload=video_start,
                    reference_uploads=refs,
                    resolution=video_resolution,
                    aspect_ratio=video_ratio,
                )

                st.session_state[
                    "last_video"
                ] = video_bytes

                st.success(
                    "Vídeo concluído."
                )

                st.video(
                    video_bytes
                )

                st.download_button(
                    "⬇️ Baixar vídeo MP4",
                    data=video_bytes,
                    file_name="reconstrucao_historica.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )

            except Exception as exc:

                st.error(
                    f"Erro ao gerar o vídeo: {exc}"
                )


# ============================================================
# ABA — CONFIGURAÇÃO
# ============================================================

with tab_config:

    st.subheader(
        "🔑 Como configurar a API do Google Gemini"
    )

    st.markdown(
        """
### 1. Crie sua chave no Google AI Studio

1. Abra o **Google AI Studio**.
2. Entre com sua conta Google.
3. Abra a área de **API keys / Chaves de API**.
4. Crie uma nova chave em um projeto do Google Cloud.
5. Copie a chave.

A aplicação não pede sua chave em nenhum formulário: ela lê a chave do
`st.secrets["GOOGLE_API_KEY"]`.

---

### 2. Para usar no computador

Na pasta do projeto existe:

```text
.streamlit/
└── secrets.toml
````

Edite esse arquivo e coloque:

```toml
GOOGLE_API_KEY = "COLE_SUA_CHAVE_AQUI"
```

**Não publique esse arquivo no GitHub.**

O projeto deve manter o `secrets.toml` protegido pelo `.gitignore`.

---

### 3. Para publicar no Streamlit Community Cloud

No Streamlit Community Cloud:

**App → Settings → Secrets**

Cole:

```toml
GOOGLE_API_KEY = "COLE_SUA_CHAVE_AQUI"
```

Salve e reinicie/redeploy o aplicativo.

---

### 4. Teste

Depois de configurar a chave, volte para:

**Reconstruir fotografia**

Envie uma foto antiga e clique em:

**✨ RECONSTRUIR FOTOGRAFIA**

---

### Modelos incluídos

* **Nano Banana 2** — `gemini-3.1-flash-image`
* **Nano Banana Pro** — `gemini-3-pro-image`
* **Nano Banana legado** — `gemini-2.5-flash-image`
* **Veo 3.1** — `veo-3.1-generate-preview`
  """
  )

  if api_key:

  
    st.success(
        "✅ API key encontrada. "
        "A aplicação está pronta para uso."
    )
  

  else:

  
    st.error(
        "❌ API key não encontrada."
    )
  

# ============================================================

# RODAPÉ

# ============================================================

st.divider()

st.caption(
"Aplicação preparada para restauração/reconstrução histórica "
"com referências fotográficas. "
"Verifique os direitos de uso das imagens enviadas."
)

