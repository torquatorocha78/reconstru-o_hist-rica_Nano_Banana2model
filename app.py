
import io
import os
import time
from pathlib import Path

import streamlit as st
from PIL import Image
from google import genai
from google.genai import types


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Reconstrução Histórica com IA",
    page_icon="📷",
    layout="wide",
)


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
# IMAGEM
# ============================================================

def image_part(uploaded_file):
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

    for part in response.parts:
        if getattr(part, "text", None):
            explanation.append(part.text)

        if getattr(part, "inline_data", None):
            generated = part.as_image()

    if generated is None:
        raise RuntimeError(
            "A API respondeu, mas não retornou uma imagem. "
            "Verifique o modelo e tente novamente."
        )

    return generated, "\n".join(explanation)


# ============================================================
# VÍDEO
# ============================================================

def generate_video(
    client,
    prompt,
    main_image_upload,
    reference_uploads,
    resolution,
    aspect_ratio,
):
    first_image = None

    if main_image_upload is not None:
        first_image = types.Image.from_bytes(
            data=main_image_upload.getvalue(),
            mime_type=main_image_upload.type or "image/jpeg",
        )

    references = []

    for upload in reference_uploads[:3]:
        if upload is None:
            continue

        reference = types.VideoGenerationReferenceImage(
            image=types.Image.from_bytes(
                data=upload.getvalue(),
                mime_type=upload.type or "image/jpeg",
            ),
            reference_type="asset",
        )

        references.append(reference)

    config = types.GenerateVideosConfig(
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        number_of_videos=1,
        reference_images=references if references else None,
    )

    operation = client.models.generate_videos(
        model=VIDEO_MODEL,
        prompt=prompt,
        image=first_image,
        config=config,
    )

    progress = st.progress(
        0,
        text="Enviando o trabalho para o Veo...",
    )

    counter = 0

    while not operation.done:
        counter += 1

        percent = min(
            95,
            10 + counter * 5,
        )

        progress.progress(
            percent,
            text="Gerando vídeo... aguarde.",
        )

        time.sleep(10)

        operation = client.operations.get(operation)

    progress.progress(
        100,
        text="Vídeo concluído.",
    )

    if not operation.response:
        raise RuntimeError(
            "O Veo não retornou uma resposta."
        )

    if not operation.response.generated_videos:
        raise RuntimeError(
            "O Veo terminou sem retornar um vídeo."
        )

    generated_video = (
        operation.response.generated_videos[0].video
    )

    video_bytes = getattr(
        generated_video,
        "video_bytes",
        None,
    )

    if video_bytes:
        return video_bytes

    output = io.BytesIO()

    try:
        client.files.download(
            file=generated_video,
            destination=output,
        )

        return output.getvalue()

    except Exception:
        temp_file = Path("video_result.mp4")

        client.files.download(
            file=generated_video,
            destination=str(temp_file),
        )

        data = temp_file.read_bytes()

        try:
            temp_file.unlink()
        except Exception:
            pass

        return data


# ============================================================
# PROMPTS
# ============================================================

def default_reconstruction_prompt():
    return """
Reconstrua e restaure esta fotografia histórica mantendo o máximo de
fidelidade documental.

A primeira imagem é a fotografia principal.

As demais imagens são referências documentais.

Preserve rigorosamente:

- identidade das pessoas;
- rostos;
- roupas;
- posição das pessoas;
- arquitetura;
- portas;
- janelas;
- telhado;
- cercas;
- postes;
- veículos;
- estrada;
- vegetação;
- praia;
- montanhas;
- relevo;
- perspectiva;
- enquadramento;
- proporções dos elementos.

Use as imagens de referência somente para recuperar detalhes que estejam
perdidos ou pouco visíveis na fotografia principal.

Não substitua a arquitetura histórica.

Não modernize o cenário.

Não adicione carros modernos.

Não adicione prédios modernos.

Não adicione placas modernas.

Não altere os rostos.

Não invente pessoas.

Não invente construções.

Remova riscos, manchas, sujeira e deterioração.

Recupere contraste, nitidez e detalhes.

Preserve a textura natural de uma fotografia histórica.

O resultado deve parecer uma fotografia real restaurada, e não uma pintura,
ilustração ou imagem artificial.

Mantenha iluminação e perspectiva coerentes com a fotografia original.

Não adicionar texto, letreiros ou marcas d'água.
""".strip()


def default_video_prompt():
    return """
Anime esta fotografia histórica restaurada de maneira extremamente natural
e documental.

Preserve a identidade das pessoas.

Preserve rostos, roupas, arquitetura, paisagem, veículos e objetos.

Faça apenas movimentos muito discretos e plausíveis.

Movimento de câmera lento.

Pequeno movimento natural de pessoas.

Pequeno movimento de vegetação quando apropriado.

Não deformar rostos.

Não deformar mãos.

Não deformar roupas.

Não modificar casas.

Não modificar veículos.

Não modernizar o cenário.

Não adicionar pessoas.

Não adicionar prédios.

Não adicionar carros.

Não adicionar placas.

O resultado deve parecer uma filmagem documental histórica restaurada.
""".strip()


# ============================================================
# INTERFACE
# ============================================================

st.title("📷 Reconstrução Histórica com IA")

st.caption(
    "Fotografias antigas → reconstrução/restauração → vídeo histórico"
)


api_key = get_api_key()

if not api_key:
    st.warning(
        "A API key do Google Gemini ainda não foi configurada."
    )


tab_image, tab_video, tab_config = st.tabs(
    [
        "🖼️ Reconstruir fotografia",
        "🎬 Gerar vídeo",
        "⚙️ Configuração da API",
    ]
)


# ============================================================
# ABA FOTOGRAFIA
# ============================================================

with tab_image:

    st.subheader("1. Fotografia principal")

    main_photo = st.file_uploader(
        "Envie a fotografia histórica",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="main_photo",
    )

    st.subheader("2. Referências opcionais")

    col1, col2 = st.columns(2)

    with col1:

        person_ref = st.file_uploader(
            "Pessoa / família",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="person_ref",
        )

        house_ref = st.file_uploader(
            "Casa / arquitetura",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="house_ref",
        )

        sketch_ref = st.file_uploader(
            "Croqui / desenho",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="sketch_ref",
        )

    with col2:

        landscape_ref = st.file_uploader(
            "Paisagem / rua / praia",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="landscape_ref",
        )

        extra_ref = st.file_uploader(
            "Outra referência",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            key="extra_ref",
        )

    st.subheader("3. Prompt")

    prompt = st.text_area(
        "Instruções para a reconstrução",
        value=default_reconstruction_prompt(),
        height=400,
        key="image_prompt",
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        model_label = st.selectbox(
            "Modelo",
            list(IMAGE_MODELS.keys()),
        )

    with col2:

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

    with col3:

        resolution = st.selectbox(
            "Resolução",
            [
                "1K",
                "2K",
                "4K",
            ],
            index=1,
        )

    if main_photo:
        st.image(
            main_photo,
            caption="Fotografia principal",
            use_container_width=True,
        )

    button_disabled = not (
        api_key and main_photo
    )

    if st.button(
        "✨ RECONSTRUIR FOTOGRAFIA",
        type="primary",
        use_container_width=True,
        disabled=button_disabled,
    ):

        client = make_client()

        uploads = [
            main_photo,
            person_ref,
            house_ref,
            landscape_ref,
            sketch_ref,
            extra_ref,
        ]

        uploads = [
            item
            for item in uploads
            if item is not None
        ]

        try:

            with st.spinner(
                "A IA está reconstruindo a fotografia..."
            ):

                image, explanation = generate_image(
                    client=client,
                    prompt=prompt,
                    uploads=uploads,
                    model=IMAGE_MODELS[model_label],
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )

            st.session_state["last_image"] = image
            st.session_state["last_image_prompt"] = prompt

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
                    "Observação do modelo"
                ):
                    st.write(explanation)

        except Exception as exc:

            st.error(
                f"Erro ao gerar a fotografia: {exc}"
            )

    if "last_image" in st.session_state:

        st.divider()

        st.subheader("Resultado atual")

        result_image = st.session_state[
            "last_image"
        ]

        st.image(
            result_image,
            use_container_width=True,
        )

        output = io.BytesIO()

        result_image.save(
            output,
            format="PNG",
        )

        st.download_button(
            "⬇️ Baixar fotografia reconstruída",
            data=output.getvalue(),
            file_name="fotografia_reconstruida.png",
            mime="image/png",
            use_container_width=True,
        )


# ============================================================
# ABA VÍDEO
# ============================================================

with tab_video:

    st.subheader(
        "🎬 Transformar fotografia em vídeo"
    )

    generated_image = st.session_state.get(
        "last_image"
    )

    if generated_image is not None:

        st.image(
            generated_image,
            caption="Reconstrução disponível",
```
