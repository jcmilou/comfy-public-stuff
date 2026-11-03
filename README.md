# ComfyUI workflows

Workflows y preparación personal de ComfyUI en RunPod.

## Ejemplo: extras para el template MiniMax de Hearmeman

`runpod-minimax-extras.sh` se integra con el template clonado de
[Hearmeman24/comfyui-minimax](https://github.com/Hearmeman24/comfyui-minimax).
Su runtime ejecuta `/workspace/additional_params.sh` antes de preparar modelos y
nodos. El script instala nuestras copias de nodos y amplía los JSON de
configuración de esa sesión; el instalador del autor descarga los modelos.

El script instala **ComfyUI-PromptHelper** completo, incluidos `web/extension.js`
y `web/primitive-inputs.js`, necesarios para las entradas Primitive del subgrafo.
Antes de desplegar, publique esos tres archivos bajo `custom_nodes/ComfyUI-PromptHelper/` en
la rama `main` de este repositorio. No descarga el paquete desde el repo privado
de workflows.

Además instala las copias publicadas de **OpenRouter de Gabe 1.0.2** y
**Derfuu ModdedNodes 1.0.1**, guardadas en `custom_nodes/openrouter_node/` y
`custom_nodes/derfuu_comfyui_moddednodes/`. No consulta los repositorios originales
ni el registro de ComfyUI durante el arranque. Las versiones, procedencia y hashes
están en [`runpod-node-snapshots.json`](./runpod-node-snapshots.json).

El `.sh` verifica el hash del manifiesto y de cada archivo antes de reemplazar
las copias instaladas. Los archivos sin cambios se reutilizan. No elimina chats
ni configuraciones del usuario. Los snapshots conservan los archivos publicados;
solo se excluyeron `.github/`, `.gitignore` y metadatos de instalación/caché.

Para cada copia con `requirements.txt`, el script ejecuta
`python -m pip install -r requirements.txt` con el mismo Python del hook y espera
su resultado antes de continuar. OpenRouter incluye `requests`, `tiktoken` y
`Pillow`; Derfuu no trae `requirements.txt`. No se usa `--upgrade`; pip conserva
las dependencias que ya satisfacen los requisitos y respeta `PIP_CONSTRAINT`
de la imagen. **Las versiones de estas librerías no están congeladas**: se
conservan los requisitos originales de los nodos. Un error de descarga,
verificación o pip termina el hook con error visible en los logs. El runtime
del autor puede continuar arrancando aunque falle el hook; revise los logs.

Los ocho modelos adicionales quedan registrados así:

| Carpeta de modelos | Archivo |
| --- | --- |
| `diffusion_models` | `qwen_image_2.1_int8_convrot.safetensors` |
| `diffusion_models` | `minimax_music3_dit_fp16.safetensors` |
| `text_encoders` | `qwen3vl_8b_int8_convrot.safetensors` |
| `text_encoders` | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` |
| `text_encoders` | `qwen3vl_8b_bf16.safetensors` |
| `vae` | `qwen_image_2.1_vae_bf16.safetensors` |
| `vae` | `minimax_music3_dav.safetensors` |
| `loras` | `H3_Motion_BoosterV2.safetensors` |

Las URL originales están en `EXTRA_MODELS` del `.sh`. `EXTRA_CUSTOM_NODES` sigue
vacío: los dos nodos anteriores se instalan desde las copias, no mediante clones
de terceros. No guarde tokens en este repositorio; configúrelos en RunPod.

### Configurar el template clonado

1. Mantenga la imagen Docker, los puertos y las variables del template original.
2. En **Container Start Command**, pegue esta línea una vez publicado el script
   en la rama `main` de este repositorio:

```bash
bash -c 'mkdir -p /workspace && curl -fsSL --retry 4 --retry-delay 5 --retry-all-errors https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/runpod-minimax-extras.sh -o /workspace/additional_params.sh && exec bash /start_script.sh'
```

3. Guarde el template. No necesita construir una imagen Docker propia.
4. Publique también las dos carpetas de snapshots, el manifiesto y este `.sh`
   en `main` antes de desplegar. Los hashes impiden instalar archivos incompletos
   o modificados por una conversión de fin de línea; `.gitattributes` conserva
   sus bytes originales.
5. Despliegue un pod y revise sus logs. Deben aparecer la instalación del helper,
   la instalación correcta de las copias `openrouter_node 1.0.2` y
   `derfuu_comfyui_moddednodes 1.0.1`, y el registro de ocho modelos adicionales.
   Después, el descargador original debe procesarlos.

No ejecute además este archivo desde el comando de inicio: el runtime original
lo ejecuta después de sincronizar su repositorio. El comando solo lo descarga y
entrega el control al arranque original. Si falla la descarga del script, el
comando no inicia ComfyUI, para que el fallo quede visible.

La descarga inicial del `.sh` permite hasta cinco intentos, con cinco segundos
entre reintentos. Dentro del hook, las descargas del helper, el manifiesto y las
copias de nodos permiten hasta cinco intentos ante errores de conexión, lecturas
interrumpidas o HTTP 408, 429 y 5xx. Esperan 5, 10, 15 y 20 segundos entre
intentos y muestran los reintentos en los logs. Los demás errores HTTP y los
errores de integridad siguen fallando directamente. Esto no cambia el
descargador de modelos ni la instalación de dependencias del runtime original.

Los modelos registrados se añaden a un grupo `download_personal_extras`, activo
por defecto. Puede desactivar sus descargas mediante una variable de RunPod con
ese nombre y valor `false`. Esa variable no desactiva los custom nodes añadidos.
Los reinicios no duplican las entradas. Se conservan las opciones del autor.

### Alcance

Este ejemplo depende de la interfaz actual del runtime de Hearmeman:
`TEMPLATE_DIR`, `template.json`, `src/models_registry.json` y el hook
`/workspace/additional_params.sh`. No es un script universal para cualquier imagen
ComfyUI. El arranque completo en RunPod queda pendiente de probar.

Puede usar el disco del pod durante su temporada y eliminar el pod al terminar,
tras descargar sus resultados. No necesita contratar un Network Volume para este
mecanismo. Mientras conserve discos contratados, se sigue cobrando almacenamiento.

Verificación local sin red ni instalación de paquetes: `python -B test_runpod_extras.py`.

Fuentes de la integración:

- [Hook de preparación adicional](https://github.com/Hearmeman24/comfyui-runtime/blob/stable/src/start.sh#L103-L110)
- [Configuración del template](https://github.com/Hearmeman24/comfyui-minimax/blob/master/template.json)
- [Registro de modelos](https://github.com/Hearmeman24/comfyui-minimax/blob/master/src/models_registry.json)
