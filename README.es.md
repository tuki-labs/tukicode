# TukiCode

<div align="center">
  <img src="./media/tukilogo.png" alt="TukiCode Logo" width="100"/>
  <h3>Stable Release v1.3.3</h3>
</div>

**TukiCode** es un agente de programacion CLI de codigo abierto construido en Python. Funciona localmente con Ollama o en la nube con OpenRouter, Gemini y Anthropic. Cuenta con una arquitectura completamente asincrona diseñada para un alto rendimiento y capacidad de respuesta.

---

## Novedades

- **Motor Nativo en Rust (`tuki_native`)** - Reemplaza las operaciones críticas de Python (sistema de archivos, búsqueda de código, E/S de terminal) por bindings de Rust sin costo adicional para una velocidad máxima.
- **Ejecución Paralela de Herramientas** - El agente ahora puede invocar y procesar múltiples herramientas simultáneamente en un solo turno, reduciendo drásticamente la latencia en tareas complejas.
- **Prompt Caching Integrado** - Soporte nativo para caché de contexto con Anthropic, disminuyendo el costo de tokens y mejorando radicalmente el tiempo de respuesta (TTFT).
- **Smart Background Shell** - Los comandos que tardan demasiado ya no fallan por timeout; se relegan transparentemente a un proceso en segundo plano (con monitoreo Anti-Loop inteligente) mientras la interfaz sigue mostrando su progreso en vivo.
- **Multiplataforma Auténtica** - El motor de prompts detecta dinámicamente tu sistema operativo (Windows, macOS, Linux) para adaptar los comandos de shell y las rutas de forma automática.
- **Bucle ReAct Optimizado** - La compresión de memoria de contexto ahora es no bloqueante (asíncrona), evitando que la interfaz se congele. Se previene la inflación del historial truncando salidas largas de herramientas, y el mecanismo anti-loop es más estricto para ahorrar llamadas a la API.
- **Arquitectura Asincrona** - Todos los clientes LLM utilizan metodos asincronos nativos (httpx, asyncio) para ejecucion no bloqueante y transmision mas rapida.
- **Separacion MVC** - La logica de negocio, el cambio de modelos de IA y las interacciones con la base de datos estan aisladas en un Controlador dedicado, completamente separado de la capa de interfaz de usuario.
- **Planificador Estructurado** - El planificador del agente impone estrictamente salidas estructuradas en JSON para generar planes de implementacion precisos paso a paso.
- **TUI Completa** - Interfaz a pantalla completa (Textual) con panel de chat, explorador de archivos y Consola en Vivo.
- **Terminal Interactiva (PTY)** - Pseudo-terminal real para servidores de larga duracion y comandos interactivos.
- **Soporte Multi-Proveedor** - Ollama (local), OpenRouter, Gemini, Anthropic.

---

## Instalacion

### Windows (PowerShell)

```powershell
iwr https://tukicode.site/api/install.ps1 | iex
```

Descarga `tuki.exe` a `%LOCALAPPDATA%\TukiCode\bin` y lo añade a tu PATH.

### macOS

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

**Primera ejecucion en macOS:** Si ves una advertencia de seguridad, ejecuta:

```bash
xattr -d com.apple.quarantine ~/.local/bin/tuki
```

### Linux

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

Tanto macOS como Linux instalan `tuki` en `~/.local/bin` y actualizan tu perfil de shell automaticamente.

### Desde el codigo fuente (Cualquier SO)

```bash
git clone https://github.com/tuki-labs/tukicode.git
cd tukicode
pip install -r requirements.txt
python tuki.py chat
```

---

## Inicio Rapido

```bash
# 1. Configura tu proveedor de IA
tuki config --setup

# 2. Inicia el agente
tuki chat
```

---

## Configuracion

```bash
tuki config --setup     # Asistente interactivo
tuki config             # Mostrar configuracion actual
tuki config --model     # Cambiar solo el modelo
```

### Modelos gratuitos recomendados (via OpenRouter)

| Modelo | Notas |
|---|---|
| `tencent/hy3-preview:free` | Recomendado: mejor uso de herramientas en nivel gratuito |
| `moonshotai/kimi-k2.5` | Razonamiento rapido |
| `deepseek/deepseek-chat-v3.2` | Tareas de programacion solidas |

> TukiCode requiere modelos con **soporte nativo para llamadas a herramientas** para la funcionalidad completa del agente.

---

## Modos de Operacion

TukiCode tiene tres modos de operacion distintos, seleccionables mediante tabs en la TUI. Cada uno enruta tu entrada a traves de un pipeline diferente en `core/controller.py`.

| Modo | Tab | Pipeline | Ideal para |
|---|---|---|---|
| **Chat** | Chat Mode | `AgentLoop.run_turn()` directo | Preguntas rapidas, arreglos aislados, explicaciones |
| **Plan** | Plan Mode | `Planner` → muestra pasos → **pide confirmacion** → `Executor` | Tareas de varios pasos donde quieres revisar antes de ejecutar |
| **Build** | Build Mode | `Planner` → **muestra pasos** → `Executor` inmediatamente | Generacion autonoma de proyectos completos sin interrupciones |

### Chat Mode

El agente recibe tu mensaje y entra directamente al loop ReAct. Piensa, llama herramientas, observa los resultados y repite hasta producir una `FinalResponse`. No se genera un plan estructurado: el modelo decide cada accion en tiempo real.

### Plan Mode

1. Tu mensaje se envia a `Planner.generate_plan()`, que llama al LLM y devuelve un array JSON de pasos atomicos.
2. El plan se muestra en pantalla y el agente **se pausa**, preguntando `"¿Deseas ejecutar este plan? (y/n)"`.
3. Si confirmas, `Executor.execute_plan()` ejecuta cada paso secuencialmente via `AgentLoop.run_turn()`, con reintentos y cambio de modelo en caso de fallo.

### Build Mode

1. Si existe un plan pendiente en `planner_state.json`, la ejecucion se reanuda desde el ultimo paso pendiente.
2. Si no hay plan previo, `Planner.generate_plan()` se invoca automaticamente. El plan generado se **muestra** en el chat antes de comenzar.
3. `Executor.execute_plan()` arranca inmediatamente, **sin pedir confirmacion**.

> **¿Cuando usar Build vs Plan?** Usa **Plan** cuando quieras revisar y aprobar la estrategia primero. Usa **Build** cuando confies en el agente para construir de forma autonoma y prefieras velocidad.

---

## Comandos de Chat

| Comando | Descripcion |
|---|---|
| `/help` | Lista todos los comandos disponibles |
| `/setup` | Abre el asistente de configuracion dentro del chat |
| `/model` | Cambia el modelo de IA |
| `/autonomy [low\|medium\|high]` | Controla la frecuencia con la que el agente pide confirmacion |
| `/risk [low\|medium\|high]` | Ajusta la sensibilidad de riesgo para la ejecucion de herramientas |
| `/copy [n]` | Copia el bloque de codigo `n` de la ultima respuesta |
| `/history` | Muestra las sesiones recientes |
| `/clear` | Limpia el registro del chat |
| `/exit` | Sale y guarda la sesion |

### Atajos de teclado

| Atajo | Accion |
|---|---|
| `Ctrl+S` | Parada de emergencia: detiene la ejecucion actual del agente |
| `Ctrl+B` | Alterna el panel de Consola en Vivo |
| `Ctrl+L` | Limpia el registro del chat |

---

## Requisitos

- Python 3.10+
- Uno de los siguientes:
  - **Ollama** ejecutandose localmente (`ollama serve`)
  - Clave API para **OpenRouter**, **Gemini**, o **Anthropic**

---

## Motor Nativo en Rust (`tuki_native`)

`tuki_native` es una extensión nativa escrita en Rust que se compila y se integra directamente en TukiCode (que está escrito en Python) utilizando una librería llamada PyO3.

En términos sencillos: le permite a TukiCode ejecutar sus tareas más pesadas utilizando la potencia y la velocidad extrema de Rust, mientras mantiene la facilidad de uso y la arquitectura asíncrona de Python para la lógica de negocio y la IA.

### ¿Por qué se creó?

Python es excelente para orquestar agentes de IA y hacer peticiones de red asíncronas, pero es lento para tareas intensivas de CPU y de entrada/salida (I/O). Antes de `tuki_native`, operaciones como:

- Leer y buscar dentro de miles de archivos de código en un proyecto grande.
- Construir el árbol de directorios de un repositorio completo.
- Limpiar y parsear cientos de líneas de texto de una terminal (códigos ANSI, colores, movimientos del cursor).

...bloqueaban el hilo principal de Python o tardaban demasiado, haciendo que TukiCode se sintiera un poco lento en repositorios grandes. `tuki_native` elimina estos "cuellos de botella" proporcionando bindings sin costo (zero-cost bindings), haciendo que el agente responda casi al instante en estas operaciones críticas.

### ¿Cómo está estructurado por dentro?

El código fuente en `tuki_native/src/` está dividido en módulos sumamente optimizados:

#### 1. Módulo de Sistema de Archivos (`fs.rs`)
Se encarga de recorrer el disco duro de manera ultra rápida utilizando la librería `walkdir` de Rust.
- **`get_project_tree`**: Genera el mapa/árbol del proyecto instantáneamente. Filtra automáticamente carpetas pesadas e inútiles para el contexto (como `node_modules`, `.git`, `venv`, `target`, etc.).
- **`find_files`**: Encuentra archivos por coincidencia de glob o extensión en milisegundos, saltando carpetas ignoradas a nivel de sistema operativo para no gastar recursos.
- **`list_dir`**: Lista contenidos de directorios con muchísima mayor eficiencia que el `os.listdir` de Python.

#### 2. Módulo de Búsqueda (`search.rs`)
- **`search_code`**: Reemplaza las lentas búsquedas con expresiones regulares de Python puro. Utiliza el motor de expresiones regulares de Rust (`regex`) para buscar texto o patrones dentro del código del usuario. Es capaz de rastrear de forma segura, respetando límites y filtrando por extensiones, devolviendo fragmentos con líneas de contexto.

#### 3. Módulo de Terminal/PTY (`pty.rs`)
La terminal interactiva de TukiCode genera muchísima "basura visual" (códigos de control, saltos de carro, colores ANSI). Limpiar esto en Python usando `re.sub()` en cada ejecución del loop del agente era muy costoso.
- **Limpieza ultra rápida**: Contiene funciones como `strip_control_sequences`, `strip_ansi` y `truncate_output`.
- **Optimización de Memoria**: Utiliza `OnceLock` para pre-compilar las expresiones regulares en memoria (en caché) una sola vez cuando el programa inicia. Cuando Python llama a estas funciones, el costo de CPU es prácticamente cero.

---

## Bucle ReAct Optimizado

TukiCode incorpora un bucle de razonamiento asíncrono altamente optimizado para evitar cuellos de botella y congelamientos de la interfaz, especialmente en proyectos grandes:

- **Compresión de Memoria Asíncrona:** Cuando el historial de la conversación se llena, el agente lo resume de forma 100% no bloqueante, mostrando un indicador visual sin detener la aplicación.
- **Prevención de Inflamación de Contexto (Context Bloat):** Las salidas inmensas de herramientas (como leer miles de líneas o listar directorios gigantes) se truncan automáticamente a un tamaño manejable antes de guardarse en el historial del LLM. Esto mantiene el "Time To First Token" (TTFT) extremadamente bajo y reduce costos.
- **Estimación Realista de Tokens:** El motor utiliza algoritmos ajustados para código fuente (donde abundan símbolos y palabras clave) para calcular los tokens reales en el contexto, evitando errores de límite de tokens.
- **Anti-Loop Estricto:** Si el modelo de IA comete un error y entra en un bucle ciego repitiendo la misma herramienta fallida, el motor lo interrumpe al segundo intento fallido, inyectando un mensaje correctivo y ahorrando costosas llamadas a la API.

---

## Resumen de Arquitectura

```
tuki.py              <- Punto de entrada CLI (Typer)
tuki_native/         <- Extension de alto rendimiento en Rust (PyO3)
core/
  controller.py      <- TukiController (Logica de negocio y gestion de LLM)
agent/
  loop.py            <- Bucle de razonamiento ReAct (Asincrono)
  planner.py         <- Planificador de salida JSON estructurada
  executor.py        <- Ejecutor de planes asincrono paso a paso
  clients...         <- Clientes API asincronos
tools/
  registry.py        <- Registro y despacho de herramientas
ui/
  app.py             <- Aplicacion TUI Textual
config.py            <- Gestor de configuracion TOML
```

Para documentacion tecnica mas profunda, consulta [ARCHITECTURE.md](./ARCHITECTURE.md).
