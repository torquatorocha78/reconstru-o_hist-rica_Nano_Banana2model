```python
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
    # CORREÇÃO PRINCIPAL:
    #
    # Não usar:
    # response_format={
    #     "image": {...}
    # }
    #
    # Usar image_config.
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
```
