# ComfyUI workflows

Workflows y preparación personal de ComfyUI en RunPod.

## Ejemplo: extras para el template MiniMax de Hearmeman

`runpod-minimax-extras.sh` se integra con el template clonado de
[Hearmeman24/comfyui-minimax](https://github.com/Hearmeman24/comfyui-minimax).
Su runtime ejecuta `/workspace/additional_params.sh` antes de preparar modelos y
nodos. El script amplía los JSON de configuración de esa sesión; el instalador
del autor se encarga de descargar los modelos y clonar los nodos.

**El ejemplo no añade nada todavía.** Sus dos listas están vacías y los ejemplos
están comentados. Edite `EXTRA_MODELS` y `EXTRA_CUSTOM_NODES` con lo que quiera
usar. No guarde tokens en este repositorio; configúrelos en RunPod.

### Configurar el template clonado

1. Mantenga la imagen Docker, los puertos y las variables del template original.
2. En **Container Start Command**, pegue esta línea una vez publicado el script
   en la rama `main` de este repositorio:

```bash
bash -c 'mkdir -p /workspace && curl -fsSL https://raw.githubusercontent.com/jcmilou/comfyui-workflows/main/runpod-minimax-extras.sh -o /workspace/additional_params.sh && exec bash /start_script.sh'
```

3. Guarde el template. No necesita construir una imagen Docker propia.
4. Despliegue un pod y revise sus logs. Con las listas vacías debe aparecer
   `[personal-extras] Example loaded; no extra models or nodes configured.`

No ejecute además este archivo desde el comando de inicio: el runtime original
lo ejecuta después de sincronizar su repositorio. El comando solo lo descarga y
entrega el control al arranque original. Si falla la descarga del script, el
comando no inicia ComfyUI, para que el fallo quede visible.

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

Fuentes de la integración:

- [Hook de preparación adicional](https://github.com/Hearmeman24/comfyui-runtime/blob/stable/src/start.sh#L103-L110)
- [Configuración del template](https://github.com/Hearmeman24/comfyui-minimax/blob/master/template.json)
- [Registro de modelos](https://github.com/Hearmeman24/comfyui-minimax/blob/master/src/models_registry.json)
