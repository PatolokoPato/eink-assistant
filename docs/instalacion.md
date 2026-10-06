# Guía de instalación

De cero a la pantalla funcionando en unos 30 minutos. Necesitas un PC con **Windows 10 u 11
(64 bits)**.

1. [Material](#1-material)
2. [Cableado](#2-cableado)
3. [Grabar el firmware en el ESP32](#3-grabar-el-firmware-en-el-esp32)
4. [Instalar el programa](#4-instalar-el-programa)
5. [Primer uso](#5-primer-uso)
6. [Wi-Fi (opcional)](#6-wi-fi-opcional)
7. [Conectar con Claude Desktop (opcional)](#7-conectar-con-claude-desktop-opcional)
8. [Asistente propio con clave de API (opcional)](#8-asistente-propio-con-clave-de-api-opcional)
9. [Ubicación del tiempo](#9-ubicación-del-tiempo)
10. [Problemas frecuentes](#10-problemas-frecuentes)
11. [Desinstalar](#11-desinstalar)

## 1. Material

- **Pantalla WeAct Studio 4,2" E-Paper** (400×300, controlador SSD1683), variante
  **blanco/negro/rojo**. El rojo no se usa. Para la variante solo blanco/negro, mira la
  [sección 3B](#b-compilarlo-con-el-arduino-ide).
- **ESP32-C3 SuperMini**, la placa diminuta con USB-C.
- **8 cables dupont** hembra-hembra.
- Un **cable USB-C de datos**. Muchos cables solo cargan: si Windows no detecta la placa al
  conectarla, prueba con otro.

## 2. Cableado

> ⚠️ La pantalla funciona a **3,3 V**: conecta su VCC al pin **3.3** de la placa, **nunca a 5V**.

| Pantalla WeAct | ESP32-C3 SuperMini |
|---|---|
| VCC | 3.3 |
| GND | GND |
| SDA | GPIO 6 |
| SCL | GPIO 4 |
| CS | GPIO 7 |
| D/C | GPIO 5 |
| RES | GPIO 10 |
| BUSY | GPIO 3 |

En este módulo «SDA» y «SCL» son en realidad el bus SPI (datos y reloj), no I²C.

## 3. Grabar el firmware en el ESP32

### A. Desde el navegador (recomendado, sin instalar nada)

Sirve el firmware ya compilado `esp32_eink-c3-usb-x.y.z.bin` de la página de
[Releases](https://github.com/PatolokoPato/eink-assistant/releases/latest). Esta versión funciona **por USB**. Para Wi-Fi, mira la
[sección 6](#6-wi-fi-opcional).

1. Conecta el ESP32-C3 al PC por USB.
2. Abre **[ESP Tool de Espressif](https://espressif.github.io/esptool-js/)** en **Chrome o Edge**.
   Firefox no puede acceder a puertos serie.
3. Deja *Baudrate* en 115200 y pulsa **Connect**. Elige el puerto «USB JTAG/serial debug unit»
   (o similar) y acepta.
4. En *Flash Address* pon **`0x0`**, elige el fichero `.bin` y pulsa **Program**. Tarda 1–2 minutos.
5. Cuando termine, desconecta y vuelve a conectar el cable USB.

Si no conecta: mantén pulsado el botón **BOOT** de la placa, pulsa y suelta **RST**, suelta BOOT y
vuelve a pulsar *Connect*.

### B. Compilarlo con el Arduino IDE

Hace falta para usar **Wi-Fi**, para la **variante blanco/negro** de la pantalla o para otro
panel o placa.

1. Instala el [Arduino IDE 2](https://www.arduino.cc/en/software).
2. *Herramientas → Placa → Gestor de placas*: instala **esp32 by Espressif Systems** (3.0 o
   posterior).
3. *Herramientas → Gestionar bibliotecas*: instala **GxEPD2** y **Adafruit GFX Library**.
4. Descarga este repositorio (botón verde *Code → Download ZIP*) y abre
   `firmware/esp32_eink/esp32_eink.ino`.
5. En `config.h` deja activo tu panel:
   - `EINK_PANEL_GDEY042Z98` para la WeAct blanco/negro/rojo.
   - `EINK_PANEL_GDEY042T81` para la WeAct blanco/negro.
6. Para no usar Wi-Fi, pon `#define ENABLE_WIFI 0` en `config.h`. Para usarlo, crea `secrets.h`
   (ver [sección 6](#6-wi-fi-opcional)).
7. Elige la placa en *Herramientas*:
   - **Placa**: «ESP32C3 Dev Module».
   - **USB CDC On Boot**: **Enabled**. Es imprescindible.
8. Pulsa **Subir** (→). Al terminar, cierra el monitor serie si lo abriste: el programa necesita el
   puerto para él solo.

## 4. Instalar el programa

1. Descarga `EInkAssistant-Setup-x.y.z.exe` de [Releases](https://github.com/PatolokoPato/eink-assistant/releases/latest) y ábrelo.
2. Windows puede mostrar «Windows protegió su PC» porque el instalador no está firmado. Pulsa
   **Más información → Ejecutar de todas formas**.
3. Elige las opciones:
   - **Acceso directo en el escritorio**.
   - **Iniciar con Windows**: arranca en la bandeja del sistema al encender el PC.
   - **Conectar con Claude Desktop**: si lo usas, ver [sección 7](#7-conectar-con-claude-desktop-opcional).

No pide permisos de administrador. Se instala en `%LOCALAPPDATA%\Programs\E-Ink Assistant`.

## 5. Primer uso

1. Con el ESP32 conectado por USB, abre **E-Ink Assistant**.
2. En *Conexión* deja **Automático**: el programa prueba todos los puertos COM y encuentra la
   placa solo.
3. Elige una vista en la lista y pulsa **Mostrar en la E-Ink**. El primer refresco tarda unos
   10–25 s y la pantalla parpadea: es normal en la tinta electrónica.

Detalles útiles:

- **Cerrar la ventana no cierra el programa**: sigue en la bandeja del sistema, junto al reloj,
  actualizando la pantalla. Para salir: icono de la bandeja → *Salir*.
- **Actualización automática**: cada N minutos (opción en la ventana).
- **«Refresco completo (limpia restos)»** quita cualquier sombra de imágenes anteriores.
- Las preferencias se guardan en `%APPDATA%\eink-assistant\settings.json` y el registro de
  actividad en `app.log`, en la misma carpeta.

## 6. Wi-Fi (opcional)

Con Wi-Fi, la pantalla solo necesita un cargador USB y puede estar en cualquier sitio de la casa.

1. En la carpeta del firmware, copia `secrets.example.h` como **`secrets.h`** y pon tu red:
   ```c
   #define WIFI_SSID      "nombre-de-tu-red"
   #define WIFI_PASSWORD  "tu-contraseña"
   ```
   `secrets.h` está en `.gitignore`: nunca se sube al repositorio.
2. Compila y graba el firmware con el Arduino IDE ([sección 3B](#b-compilarlo-con-el-arduino-ide)).
3. En el programa: *Conexión* → **Wi-Fi (eink.local)**. El ESP32 se anuncia en la red con ese
   nombre, así que no hace falta saber su IP.

Requisitos:

- La red tiene que ser de **2,4 GHz**: el ESP32-C3 no tiene 5 GHz.
- El PC y la pantalla tienen que estar en la **misma red**.
- Si conecta mal, cambia `WIFI_TX_POWER` en `config.h`. Algunas placas C3 SuperMini conectan mejor
  con menos potencia y otras con más.

Mientras no consigue conectarse, el firmware envía mensajes de diagnóstico por USB, que aparecen en
`app.log`: el estado, el motivo del fallo y si ve la red.

## 7. Conectar con Claude Desktop (opcional)

Con esto, [Claude Desktop](https://claude.ai/download) puede escribir en la pantalla: «muéstrame
en la pantallita la receta», «pon en la E-Ink los pasos»… No necesita clave de API: usa tu cuenta
de Claude.

1. Marca **Conectar con Claude Desktop** al instalar, o en el programa pulsa **Conectar con Claude
   Desktop…** (en *Opciones*).
2. Te pedirá que cierres Claude Desktop **del todo**: icono de Claude en la bandeja → *Quit*.
   Cerrar la ventana no basta, porque Claude reescribe su configuración al salir.
3. Vuelve a abrir Claude Desktop. En *Configuración → Desarrollador* debería aparecer **eink**.

**El programa E-Ink Assistant tiene que estar abierto** (basta en la bandeja): Claude le manda
el texto y el programa lo dibuja.

Para que Claude envíe **todas** sus respuestas a la pantalla sin pedírselo, marca en el programa
*«Claude Desktop envía todas sus respuestas»* y reinicia Claude Desktop.

## 8. Asistente propio con clave de API (opcional)

El botón **✦ Abrir asistente…** del programa permite preguntar a Claude directamente, sin Claude
Desktop. Usa la API de Anthropic, que se paga por uso:

1. Crea una clave en [console.anthropic.com](https://console.anthropic.com) → *API Keys*.
2. Guárdala como variable de entorno de tu usuario. En PowerShell:
   ```powershell
   [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
   ```
3. Cierra el programa desde la bandeja y vuelve a abrirlo.

## 9. Ubicación del tiempo

Por defecto muestra el tiempo de **Madrid**. Para el de tu ciudad, en PowerShell:

```powershell
[Environment]::SetEnvironmentVariable("EINK_CITY", "Valencia", "User")
```

Si el nombre es ambiguo, usa coordenadas, que tienen prioridad sobre el nombre:

```powershell
[Environment]::SetEnvironmentVariable("EINK_LAT", "39.47", "User")
[Environment]::SetEnvironmentVariable("EINK_LON", "-0.38", "User")
```

Después, cierra el programa desde la bandeja y vuelve a abrirlo.

## 10. Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| Windows no detecta la placa (no aparece ningún COM nuevo) | Cable que solo carga: prueba otro cable USB-C de datos |
| «El ESP32 no responde» | Cierra el monitor serie del Arduino IDE; comprueba que grabaste el firmware con *USB CDC On Boot: Enabled* |
| «La pantalla no responde (BUSY ocupado)» | Revisa el cableado, sobre todo BUSY (GPIO 3), VCC y GND |
| La imagen sale desplazada o con basura | Panel equivocado en `config.h` (blanco/negro frente a tres colores) |
| Se ve la imagen anterior "fantasma" debajo | Pulsa «Refresco completo (limpia restos)» |
| Wi-Fi: «No se encuentra eink.local» | La placa no está en la misma red que el PC, o la red es de 5 GHz; mira `app.log` |
| El COM aparece y desaparece | La placa se reinicia: alimentación insuficiente o cortocircuito en los cables |
| Claude Desktop no muestra la herramienta «eink» | Repite la sección 7 cerrando Claude **desde la bandeja**; el programa debe estar abierto |

## 11. Desinstalar

*Configuración de Windows → Aplicaciones → E-Ink Assistant → Desinstalar.*

Tus preferencias quedan en `%APPDATA%\eink-assistant`; puedes borrar esa carpeta a mano. Si lo
conectaste con Claude Desktop, quita la entrada `"eink"` de su configuración (*Configuración →
Desarrollador → Editar configuración*).
