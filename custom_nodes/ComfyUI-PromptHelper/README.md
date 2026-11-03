# ComfyUI-PromptHelper: OpenRouter / Local

Copie esta carpeta a `ComfyUI/custom_nodes/ComfyUI-PromptHelper` y reinicie
ComfyUI. No necesita otro entorno de Python ni un servidor LLM adicional.
OpenRouter utiliza el paquete `ComfyUI-Openrouter_node` existente; la ruta Local
no necesita que ese paquete esté instalado. No requiere dependencias nuevas.

El nodo nuevo **Prompt Helper · OpenRouter / Local** conserva las tres salidas:
`prompt`, `request_preview` y `stats`. El nodo anterior `PromptHelperOpenRouter`
sigue disponible con su distribución de widgets para workflows existentes.

## Generación local

- Seleccione `backend = Local` y conecte un `CLIPLoader` a `clip`.
- Use un encoder con capacidad de generar texto, no cualquier encoder de difusión.
  El workflow de ejemplo conecta el Qwen3-VL 8B int8 ya seleccionado por el usuario.
  No se descargan pesos automáticamente; el archivo debe estar instalado.
- Mantiene el mismo mensaje de sistema editable y el mismo brief del usuario que
  OpenRouter. No añade otra llamada para analizar imágenes o reescribir la salida.
- `send_images_to_llm` también se aplica a Local: con visión envía las referencias
  compactadas en el mismo orden que las salidas hacia Qwen. Cada imagen conserva
  su tamaño y tensor; no se concatenan ni redimensionan. Sin visión conserva las
  descripciones, roles y triggers, pero omite los píxeles.
- La implementación usa `Generate Text` nativo y la lista de imágenes de los
  tokenizers Qwen3-VL / Qwen3.5. Si el tokenizer no adjunta todas las imágenes,
  muestra un error de compatibilidad; no continúa simulando que las vio.
- `local_max_length` limita los tokens de salida, incluido el razonamiento. Los
  parámetros `local_*` solo afectan a Local. La temperatura sigue dependiendo de
  Fidelidad / Medio / Libertad. Fidelidad local usa generación sin sampling.
- `local_seed` controla el muestreo; `regenerate` conserva su función de invalidar
  la caché. Con la misma seed y entradas, una nueva ejecución local puede repetir
  el resultado. El razonamiento se separa del prompt como hace Generate Text.
- La entrada CLIP es lazy: OpenRouter y el prompt manual no ejecutan su loader.
  `manual_prompt` devuelve el texto exacto sin generación local ni remota.
- `request_preview` muestra los mensajes y parámetros reales, sin claves ni
  píxeles. `stats` indica Local sin presentar tokens o costos inventados.

## Workflow integrado

Los workflows se mantienen en el repositorio privado `comfyui-workflows`.
Desde allí, importe `qwen-ref-26-11-02-local.json` tras instalar este paquete.
Añade el selector de backend y un loader independiente para el
redactor principal. La sección Extras y las demás conexiones permanecen iguales.
El original `qwen-ref-26-11-02.json` se conserva. Los controles avanzados locales
se encuentran dentro del subgrafo, en el nuevo redactor.

Se pueden conectar los `Primitive` normales de ComfyUI a `model`, `writing_mode`
y `backend`, tanto directamente al redactor como desde las entradas del subgrafo.
La extensión web del paquete corrige esos tres valores al preparar la petición:
resuelve los cables del snapshot de ejecución y conserva el valor del Primitive
en la entrada del redactor, aunque el control interno muestre un valor anterior.
No modifica los widgets ni las definiciones compartidas; dos instancias de un
subgrafo pueden usar selecciones distintas. También conserva las conexiones de
los selectores ejecutables de este paquete.
El modelo inicial del nodo nuevo queda vacío y exige selección explícita para
OpenRouter. La copia del workflow conserva el modelo que estaba seleccionado
afuera y no contiene el antiguo `openai/gpt-4o` interno. Importar de nuevo la
copia actualizada después de instalar el paquete y reiniciar ComfyUI. Para añadir
esta corrección a un workflow existente basta instalar el paquete completo,
reiniciar ComfyUI y recargar la página; no hace falta reconstruir el subgrafo.

Reconstrucción y pruebas desde la raíz de `comfyui-workflows`, manteniendo este
repositorio `comfy-public-stuff` como carpeta hermana:

```powershell
python -B build_qwen_local_helper.py
python -B test_prompt_helper_local.py
node test_frontend_selector_routing.mjs
```

Las pruebas ejecutan las clases instaladas de Generate Text y de los tokenizers
Qwen con el tokenizador base y la generación simulados. Comprueban dos rutas,
diez referencias de distintos tamaños, parámetros, caché lazy, separación del
razonamiento, compatibilidad anterior y conexiones del workflow. No cargan pesos,
usan GPU ni llaman APIs. La inferencia y la importación reales quedan pendientes.

## RunPod

La raíz de `comfy-public-stuff` contiene `runpod-minimax-extras.sh`. Instala
este paquete en `/ComfyUI/custom_nodes/ComfyUI-PromptHelper` mediante sus URLs raw,
incluidos los dos archivos JavaScript de `web/`. Copiar solo `__init__.py` omite
la corrección de las entradas Primitive.
El script conserva la extensión de modelos y otros repositorios del ejemplo.
No basta añadir el repositorio de workflows a `EXTRA_CUSTOM_NODES`, porque el
módulo está dentro de una subcarpeta y ComfyUI no lo descubriría en la raíz.

La estructura publicada en `jcmilou/comfy-public-stuff` es:

```text
runpod-minimax-extras.sh
custom_nodes/
    ComfyUI-PromptHelper/
        __init__.py
        README.md
        web/
            extension.js
            primitive-inputs.js
```

El comando de inicio está en el README de la raíz del repo público. Las URLs raw
del script y sus tres archivos de código se verificaron después de publicarlos.
El arranque completo en RunPod queda pendiente de prueba. El hook falla si no
puede descargar el paquete; el runtime del autor puede continuar el arranque,
por lo que hay que comprobar sus logs.
