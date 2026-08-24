# Cómo entregar la documentación al cliente

La guía operativa vive en Markdown (para el equipo técnico). Para **Traldis Porta** u otro cliente, conviene entregar **PDF** o **Word**.

---

## Opción 1 — PDF desde HTML (recomendada)

1. Regenerar la versión cliente (cada vez que cambie la guía):

   ```bash
   python tools/export_guia_cliente.py
   ```

2. Abrir en Chrome o Edge:

   `aduanas_transport/doc/GUIA_TRALDIS_PORTA_CLIENTE.html`

3. **Ctrl+P** → Destino: **Guardar como PDF**

4. Ajustes recomendados:
   - Tamaño: **A4**
   - Márgenes: **Predeterminados**
   - Activar **Gráficos de fondo** (para la portada)
   - Encabezado/pie: opcional (nombre cliente, fecha)

5. Enviar el PDF al cliente por email o carpeta compartida.

El HTML incluye portada, tablas con estilo y texto sin enlaces internos al repositorio.

---

## Opción 2 — Microsoft Word

1. Generar el HTML como arriba.
2. Abrir el `.html` con **Word** (clic derecho → Abrir con → Word).
3. Revisar tablas y saltos de página.
4. **Guardar como** → `.docx`.
5. Opcional: insertar logo Traldis en la portada antes de guardar.

Ventaja: el cliente puede comentar o firmar revisión en Word.

---

## Opción 3 — Pandoc (PDF directo, si está instalado)

```bash
pandoc aduanas_transport/doc/GUIA_TRALDIS_PORTA.md -o Guia_Traldis_Porta.pdf --pdf-engine=xelatex -V lang=es
```

Requiere [Pandoc](https://pandoc.org/) y una distribución LaTeX. Útil si ya lo tenéis en CI; la portada habría que añadirla aparte.

---

## Opción 4 — Presentación ejecutiva (1 h)

Para una reunión de entrega, podéis extraer de la guía:

| Diapositiva | Contenido |
|-------------|-----------|
| 1 | Qué es el módulo (export AES + import H1) |
| 2 | Rol Traldis (agente + transportista, indirecta) |
| 3 | Flujo export (diagrama 7 pasos) |
| 4 | Flujo import sin DDT (5 pasos) |
| 5 | Documentos: factura sí, PDF DUA interno |
| 6 | Configuración: certificado + endpoints |
| 7 | Checklist operador + soporte |

Copiar tablas y diagramas de `GUIA_TRALDIS_PORTA.md` a PowerPoint o Google Slides.

---

## Qué enviar al cliente

| Entregable | Audiencia |
|------------|-----------|
| `GUIA_TRALDIS_PORTA_CLIENTE.pdf` | Operadores aduanas, responsables logística |
| Acceso Odoo + certificado configurado | Administrador |
| `CONFIGURAR_CERTIFICADO_AEAT.md` (como PDF aparte) | IT / admin |

No hace falta entregar el código ni los `.md` del repo salvo que pidan documentación técnica de mantenimiento.

---

## Mantener actualizado

1. Editar `aduanas_transport/doc/GUIA_TRALDIS_PORTA_CLIENTE.md`.
2. Ejecutar `python tools/export_guia_cliente.py`.
3. Regenerar PDF y subir versión (p. ej. `Guia_Traldis_Porta_v1.1.pdf`).

Incrementar `VERSION` en `tools/export_guia_cliente.py` cuando entreguéis una revisión formal al cliente.
