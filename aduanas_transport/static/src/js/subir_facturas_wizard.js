/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, "aduanas_transport.SubirFacturasWizard", {
    onMounted() {
        if (this.props.resModel === "aduanas.subir.facturas.wizard") {
            // Configurar drag and drop después de que el componente esté montado
            setTimeout(() => {
                this._setupDragAndDrop();
            }, 300);
        }
    },

    _setupDragAndDrop() {
        // Esperar a que el DOM esté listo
        setTimeout(() => {
            const dropZone = document.querySelector('.drop-zone-facturas');
            if (!dropZone) return;

            // Prevenir comportamientos por defecto
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, this._preventDefaults, false);
                document.body.addEventListener(eventName, this._preventDefaults, false);
            });

            // Resaltar el área cuando se arrastra sobre ella
            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => {
                    dropZone.classList.add('drag-over');
                }, false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => {
                    dropZone.classList.remove('drag-over');
                }, false);
            });

            // Manejar el drop
            dropZone.addEventListener('drop', (e) => {
                this._handleDrop(e);
            }, false);

            // Manejar click en el área para abrir selector de archivos
            const fileInput = dropZone.querySelector('input[type="file"]');
            if (fileInput) {
                dropZone.addEventListener('click', () => {
                    fileInput.click();
                });
                fileInput.addEventListener('change', (e) => {
                    this._handleFiles(e.target.files);
                });
            }
        }, 500);
    },

    _preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    },

    async _handleDrop(e) {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this._handleFiles(files);
        }
    },

    async _handleFiles(files) {
        const pdfFiles = Array.from(files).filter(file => 
            file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
        );

        if (pdfFiles.length === 0) {
            this.env.services.notification.add(
                "Por favor, selecciona solo archivos PDF",
                { type: "warning" }
            );
            return;
        }

        // Obtener el recordset del wizard
        const record = this.model.root;
        if (!record) return;

        // Leer todos los archivos primero
        const filesData = [];
        for (const file of pdfFiles) {
            try {
                const base64 = await this._fileToBase64(file);
                filesData.push({
                    name: file.name,
                    factura_pdf: base64,
                    factura_pdf_filename: file.name,
                });
            } catch (error) {
                console.error("Error procesando archivo:", file.name, error);
                this.env.services.notification.add(
                    `Error al procesar ${file.name}: ${error.message}`,
                    { type: "danger" }
                );
            }
        }

        // Agregar todas las líneas de una vez
        if (filesData.length > 0) {
            const currentLines = record.data.factura_ids || [];
            const newLines = filesData.map(fileData => [0, 0, fileData]);
            
            await record.update({
                factura_ids: [...currentLines, ...newLines]
            });

            this.env.services.notification.add(
                `${filesData.length} archivo(s) agregado(s) correctamente`,
                { type: "success" }
            );
        }
    },

    _fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                // El resultado incluye el prefijo "data:application/pdf;base64,"
                // Necesitamos solo la parte base64
                const base64String = reader.result.split(',')[1];
                resolve(base64String);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    },
});

