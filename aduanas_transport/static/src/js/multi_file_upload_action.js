/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MultiFileUploadAction extends Component {
    static template = "aduanas_transport.MultiFileUploadAction";
    
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        
        // Obtener parámetros de la acción
        this.cargaMasivaId = this.props.params?.carga_masiva_id;
        this.model = this.props.params?.model || "aduana.carga.masiva";
        this.method = this.props.params?.method || "action_subir_facturas_multiple";
        
        // Abrir el selector de archivos automáticamente
        this.openFileSelector();
    }
    
    async openFileSelector() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'application/pdf,.pdf';
        input.multiple = true;
        input.style.display = 'none';
        input.addEventListener('change', (ev) => this.onMultiFileSelect(ev));
        document.body.appendChild(input);
        input.click();
        setTimeout(() => {
            if (document.body.contains(input)) {
                document.body.removeChild(input);
            }
            // Cerrar la acción después de un breve momento
            this.close();
        }, 100);
    }
    
    async onMultiFileSelect(ev) {
        const files = ev.target.files;
        if (!files || files.length === 0) {
            this.close();
            return;
        }

        this.notification.add("Procesando archivos...", { type: "info" });

        // Convertir todos los archivos a base64
        const filePromises = Array.from(files).map(file => {
            return new Promise((resolve, reject) => {
                if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
                    reject(new Error(`El archivo ${file.name} no es un PDF`));
                    return;
                }

                const reader = new FileReader();
                reader.onload = (e) => {
                    const base64Content = e.target.result.split(',')[1];
                    resolve({
                        name: file.name,
                        content: base64Content,
                    });
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        });

        try {
            const filesData = await Promise.all(filePromises);

            // Llamar al método Python
            await this.orm.call(
                this.model,
                this.method,
                [[this.cargaMasivaId]],
                { files_data: filesData }
            );

            this.notification.add(
                `Se subieron ${filesData.length} archivo(s) correctamente`,
                { type: "success" }
            );

            // Recargar la vista
            this.close();
            await this.action.doAction("reload");

        } catch (error) {
            console.error("Error subiendo archivos:", error);
            this.notification.add(
                error.message || "Error al subir los archivos",
                { type: "danger" }
            );
            this.close();
        }
    }
    
    close() {
        // Cerrar esta acción
        if (this.props.close) {
            this.props.close();
        }
    }
}

// Registrar la acción de cliente
registry.category("actions").add("multi_file_upload", MultiFileUploadAction);











