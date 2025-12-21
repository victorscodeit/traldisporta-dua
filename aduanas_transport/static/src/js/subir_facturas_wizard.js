/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Variable global para rastrear si ya se configuró el listener global
let globalObserverSetup = false;
let activeWizardController = null;

// Función para configurar drag and drop en un elemento
function setupDragAndDropForElement(dropZone, controller) {
    console.log("[SubirFacturas] Configurando drag and drop para:", dropZone);
    
    // Si ya está configurado, no hacer nada
    if (dropZone._listenersSetup) {
        console.log("[SubirFacturas] Ya configurado, omitiendo");
        return;
    }
    
    dropZone._listenersSetup = true;
    
    const fileInput = dropZone.querySelector('input[type="file"]');
    if (!fileInput) {
        console.error("[SubirFacturas] No se encontró el input de archivos");
        return;
    }
    
    console.log("[SubirFacturas] Input encontrado:", fileInput);
    
    // Prevenir comportamientos por defecto
    const preventDefaults = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };
    
    // Handler para drag and drop
    const dragEnterHandler = (e) => {
        console.log("[SubirFacturas] dragenter");
        preventDefaults(e);
        dropZone.classList.add('drag-over');
    };
    
    const dragOverHandler = (e) => {
        preventDefaults(e);
        dropZone.classList.add('drag-over');
    };
    
    const dragLeaveHandler = (e) => {
        preventDefaults(e);
        if (!dropZone.contains(e.relatedTarget)) {
            dropZone.classList.remove('drag-over');
        }
    };
    
    const dropHandler = (e) => {
        console.log("[SubirFacturas] drop event", e.dataTransfer.files.length, "archivos");
        preventDefaults(e);
        dropZone.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files && files.length > 0 && controller) {
            controller._handleFiles(files);
        }
    };
    
    // Handler para click
    const clickHandler = (e) => {
        console.log("[SubirFacturas] click en:", e.target);
        // No hacer nada si es un botón
        if (e.target.closest('button, footer, .o_form_button')) {
            return;
        }
        // No hacer nada si el click es directamente en el input
        if (e.target === fileInput || e.target.type === 'file') {
            return;
        }
        // Si el click es dentro de la zona de drop
        if (dropZone.contains(e.target)) {
            console.log("[SubirFacturas] Abriendo selector de archivos");
            e.preventDefault();
            e.stopPropagation();
            // Usar setTimeout para asegurar que el click se procese correctamente
            setTimeout(() => {
                fileInput.click();
            }, 0);
        }
    };
    
    // Handler para cambio del input
    const changeHandler = (e) => {
        console.log("[SubirFacturas] change event", e.target.files.length, "archivos");
        const files = e.target.files;
        if (files && files.length > 0 && controller) {
            controller._handleFiles(files);
        }
        e.target.value = '';
    };
    
    // Agregar listeners
    dropZone.addEventListener('dragenter', dragEnterHandler, { passive: false });
    dropZone.addEventListener('dragover', dragOverHandler, { passive: false });
    dropZone.addEventListener('dragleave', dragLeaveHandler, { passive: false });
    dropZone.addEventListener('drop', dropHandler, { passive: false });
    dropZone.addEventListener('click', clickHandler, true); // Usar capture phase
    fileInput.addEventListener('change', changeHandler);
    
    // Guardar referencias para limpieza
    dropZone._dragHandlers = {
        dragenter: dragEnterHandler,
        dragover: dragOverHandler,
        dragleave: dragLeaveHandler,
        drop: dropHandler,
        click: clickHandler,
        change: changeHandler,
        fileInput: fileInput
    };
    
    console.log("[SubirFacturas] Listeners configurados correctamente");
}

// Función para limpiar drag and drop
function cleanupDragAndDropForElement(dropZone) {
    if (!dropZone || !dropZone._listenersSetup) {
        return;
    }
    
    const handlers = dropZone._dragHandlers;
    if (handlers) {
        dropZone.removeEventListener('dragenter', handlers.dragenter);
        dropZone.removeEventListener('dragover', handlers.dragover);
        dropZone.removeEventListener('dragleave', handlers.dragleave);
        dropZone.removeEventListener('drop', handlers.drop);
        dropZone.removeEventListener('click', handlers.click, true);
        if (handlers.fileInput) {
            handlers.fileInput.removeEventListener('change', handlers.change);
        }
    }
    
    dropZone._listenersSetup = false;
    dropZone._dragHandlers = null;
}

// Configurar observer global para detectar cuando se abre el wizard
function setupGlobalObserver() {
    if (globalObserverSetup) {
        return;
    }
    globalObserverSetup = true;
    
    console.log("[SubirFacturas] Configurando observer global");
    
    const observer = new MutationObserver((mutations) => {
        // Buscar el elemento drop-zone-facturas
        const dropZone = document.querySelector('.drop-zone-facturas');
        if (dropZone && !dropZone._listenersSetup && activeWizardController) {
            console.log("[SubirFacturas] DropZone detectado por observer global");
            setupDragAndDropForElement(dropZone, activeWizardController);
        }
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    // También intentar periódicamente como fallback
    const intervalId = setInterval(() => {
        const dropZone = document.querySelector('.drop-zone-facturas');
        if (dropZone && !dropZone._listenersSetup && activeWizardController) {
            console.log("[SubirFacturas] DropZone detectado por intervalo");
            setupDragAndDropForElement(dropZone, activeWizardController);
            clearInterval(intervalId);
        }
    }, 500);
    
    // Limpiar después de 10 segundos
    setTimeout(() => clearInterval(intervalId), 10000);
}

// Guardar referencias a los métodos originales antes del patch
const originalSetup = FormController.prototype.setup;
const originalOnMounted = FormController.prototype.onMounted;
const originalOnWillUnmount = FormController.prototype.onWillUnmount;

patch(FormController.prototype, "aduanas_transport.SubirFacturasWizard", {
    setup() {
        // Llamar al setup original si existe
        if (originalSetup) {
            originalSetup.call(this);
        }
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");
        
        if (this.props.resModel === "aduanas.subir.facturas.wizard") {
            console.log("[SubirFacturas] Setup llamado para wizard");
            activeWizardController = this;
            setupGlobalObserver();
            
            // Intentar configurar después de un delay
            setTimeout(() => {
                const dropZone = document.querySelector('.drop-zone-facturas');
                if (dropZone) {
                    console.log("[SubirFacturas] DropZone encontrado en setup");
                    setupDragAndDropForElement(dropZone, this);
                }
            }, 500);
        }
    },

    onMounted() {
        // Llamar al onMounted original si existe
        if (originalOnMounted) {
            originalOnMounted.call(this);
        }
        if (this.props.resModel === "aduanas.subir.facturas.wizard") {
            console.log("[SubirFacturas] onMounted llamado");
            activeWizardController = this;
            
            setTimeout(() => {
                const dropZone = document.querySelector('.drop-zone-facturas');
                if (dropZone) {
                    console.log("[SubirFacturas] DropZone encontrado en onMounted");
                    setupDragAndDropForElement(dropZone, this);
                }
            }, 200);
        }
    },

    onWillUnmount() {
        if (this.props.resModel === "aduanas.subir.facturas.wizard") {
            console.log("[SubirFacturas] onWillUnmount llamado");
            const dropZone = document.querySelector('.drop-zone-facturas');
            if (dropZone) {
                cleanupDragAndDropForElement(dropZone);
            }
            if (activeWizardController === this) {
                activeWizardController = null;
            }
        }
        // Llamar al onWillUnmount original si existe
        if (originalOnWillUnmount) {
            originalOnWillUnmount.call(this);
        }
    },

    async _handleFiles(files) {
        console.log("_handleFiles llamado con", files.length, "archivo(s)");
        const pdfFiles = Array.from(files).filter(file => 
            file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
        );
        
        console.log("Archivos PDF filtrados:", pdfFiles.length);

        if (pdfFiles.length === 0) {
            this.notification.add(
                "Por favor, selecciona solo archivos PDF",
                { type: "warning" }
            );
            return;
        }

        // Obtener el recordset del wizard
        const record = this.model.root;
        if (!record) {
            console.error("No se pudo obtener el record del wizard");
            this.notification.add(
                "Error: No se pudo acceder al formulario. Por favor, recarga la página.",
                { type: "danger" }
            );
            return;
        }

        // Mostrar notificación de procesamiento
        this.notification.add(
            `Procesando ${pdfFiles.length} archivo(s)...`,
            { type: "info" }
        );

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
                this.notification.add(
                    `Error al procesar ${file.name}: ${error.message}`,
                    { type: "danger" }
                );
            }
        }

        // Agregar archivos usando método Python
        if (filesData.length > 0) {
            try {
                // Obtener el ID del wizard
                let wizardId = record.resId;
                
                // Si el wizard no tiene ID aún, guardarlo primero para obtener el ID
                if (!wizardId) {
                    // Guardar el wizard para obtener su ID
                    await record.save();
                    wizardId = record.resId;
                    console.log("[SubirFacturas] Wizard creado con ID:", wizardId);
                }

                if (!wizardId) {
                    throw new Error("No se pudo obtener el ID del wizard");
                }

                console.log("[SubirFacturas] Wizard ID:", wizardId);
                console.log("[SubirFacturas] Archivos a agregar:", filesData.length);

                // Llamar al método Python para agregar los archivos
                await this.orm.call(
                    "aduanas.subir.facturas.wizard",
                    "action_agregar_archivos",
                    [[wizardId]],
                    { files_data: filesData }
                );

                console.log("[SubirFacturas] Archivos agregados correctamente en backend");

                // Esperar un momento para que se procese en el backend
                // Aumentar el delay para asegurar que los datos estén completamente guardados
                await new Promise(resolve => setTimeout(resolve, 500));

                // Obtener las líneas recién creadas desde el backend
                // Leer varias veces si es necesario para asegurar que tenemos los datos más recientes
                let wizardData = null;
                let attempts = 0;
                const maxAttempts = 3;
                
                while (attempts < maxAttempts && (!wizardData || !wizardData[0] || !wizardData[0].factura_ids || wizardData[0].factura_ids.length === 0)) {
                    wizardData = await this.orm.read(
                        "aduanas.subir.facturas.wizard",
                        [wizardId],
                        ["factura_ids"]
                    );
                    console.log(`[SubirFacturas] Intento ${attempts + 1}: Datos del wizard desde backend:`, wizardData);
                    
                    if (wizardData && wizardData[0] && wizardData[0].factura_ids && wizardData[0].factura_ids.length > 0) {
                        break;
                    }
                    
                    attempts++;
                    if (attempts < maxAttempts) {
                        await new Promise(resolve => setTimeout(resolve, 200));
                    }
                }

                console.log("[SubirFacturas] Datos finales del wizard:", wizardData);

                if (wizardData && wizardData[0] && wizardData[0].factura_ids) {
                    // Obtener los IDs de las líneas desde el backend
                    const lineIdsFromBackend = wizardData[0].factura_ids;
                    console.log("[SubirFacturas] IDs de líneas desde backend:", lineIdsFromBackend);

                    // Obtener las líneas actuales del record (si hay)
                    const currentFacturaIds = record.data.factura_ids;
                    let currentLineIds = [];
                    
                    if (currentFacturaIds) {
                        if (Array.isArray(currentFacturaIds)) {
                            // Si es un array de comandos, extraer los IDs
                            currentFacturaIds.forEach(cmd => {
                                if (Array.isArray(cmd) && cmd.length >= 2) {
                                    if (cmd[0] === 4) {
                                        // Comando [4, id] - vincular existente
                                        currentLineIds.push(cmd[1]);
                                    } else if (cmd[0] === 1 && cmd[1]) {
                                        // Comando [1, id, data] - actualizar existente
                                        currentLineIds.push(cmd[1]);
                                    }
                                }
                            });
                        } else if (currentFacturaIds.records) {
                            // Si es un RecordList, obtener los IDs
                            const records = Array.from(currentFacturaIds.records || []);
                            currentLineIds = records.map(rec => rec.id).filter(id => id && id > 0);
                        }
                    }

                    console.log("[SubirFacturas] IDs de líneas actuales en record:", currentLineIds);

                    // Combinar: mantener las existentes y agregar las nuevas
                    // Usar [6, 0, [ids]] para reemplazar todas con la lista completa desde el backend
                    // Esto asegura que tenemos todas las líneas (existentes + nuevas)
                    await record.update({
                        factura_ids: [[6, 0, lineIdsFromBackend]]
                    });

                    console.log("[SubirFacturas] Record actualizado con todas las líneas desde backend");

                    // Recargar el modelo completo
                    await this.model.root.load();

                    console.log("[SubirFacturas] Modelo recargado, factura_ids:", this.model.root.data.factura_ids);

                    // Forzar actualización del campo One2many
                    const facturaIdsField = this.model.root.data.factura_ids;
                    if (facturaIdsField) {
                        // Intentar recargar el campo si tiene método load
                        if (facturaIdsField.load && typeof facturaIdsField.load === 'function') {
                            try {
                                await facturaIdsField.load();
                                console.log("[SubirFacturas] Campo factura_ids recargado");
                            } catch (e) {
                                console.log("[SubirFacturas] Error recargando campo:", e);
                            }
                        }
                    }

                    // Notificar cambios en el modelo para que la vista se actualice
                    if (this.model.root.notify) {
                        this.model.root.notify();
                        console.log("[SubirFacturas] Cambios notificados al modelo");
                    }

                    // Forzar re-render después de un delay más largo para asegurar que los datos estén guardados
                    setTimeout(async () => {
                        // Leer nuevamente desde el backend para obtener los datos más recientes
                        const latestWizardData = await this.orm.read(
                            "aduanas.subir.facturas.wizard",
                            [wizardId],
                            ["factura_ids"]
                        );
                        
                        if (latestWizardData && latestWizardData[0] && latestWizardData[0].factura_ids) {
                            const latestLineIds = latestWizardData[0].factura_ids;
                            console.log("[SubirFacturas] IDs más recientes desde backend en setTimeout:", latestLineIds);
                            
                            // Actualizar el record con los datos más recientes
                            await record.update({
                                factura_ids: [[6, 0, latestLineIds]]
                            });
                            console.log("[SubirFacturas] Record actualizado con datos más recientes en setTimeout");
                        }

                        // Recargar el modelo una vez más para asegurar que tenemos los datos más recientes
                        await this.model.root.load();
                        console.log("[SubirFacturas] Modelo recargado nuevamente en setTimeout");

                        // Re-render del controlador
                        if (this.render && typeof this.render === 'function') {
                            this.render();
                            console.log("[SubirFacturas] Controlador re-renderizado");
                        }

                        // Disparar evento change en el campo del DOM para forzar actualización visual
                        const facturaFieldElement = document.querySelector('field[name="factura_ids"]');
                        if (facturaFieldElement) {
                            console.log("[SubirFacturas] Disparando evento change en campo DOM");
                            facturaFieldElement.dispatchEvent(new Event('change', { bubbles: true }));
                            
                            // También buscar el componente de la lista y forzar su actualización
                            const listView = facturaFieldElement.querySelector('.o_list_view, .o_list_table, table');
                            if (listView) {
                                console.log("[SubirFacturas] Lista encontrada, forzando actualización");
                                // Disparar evento en la lista
                                listView.dispatchEvent(new Event('update', { bubbles: true }));
                                listView.dispatchEvent(new Event('reload', { bubbles: true }));
                            }
                        }

                        // Intentar forzar actualización del campo One2many una vez más
                        const facturaIdsField = this.model.root.data.factura_ids;
                        if (facturaIdsField && facturaIdsField.load) {
                            try {
                                await facturaIdsField.load();
                                console.log("[SubirFacturas] Campo recargado nuevamente en setTimeout");
                            } catch (e) {
                                console.log("[SubirFacturas] Error en recarga final:", e);
                            }
                        }
                    }, 500);
                }

                this.notification.add(
                    `${filesData.length} archivo(s) agregado(s) correctamente`,
                    { type: "success" }
                );
            } catch (error) {
                console.error("[SubirFacturas] Error agregando archivos:", error);
                console.error("[SubirFacturas] Stack:", error.stack);
                this.notification.add(
                    `Error al agregar archivos: ${error.message || error}`,
                    { type: "danger" }
                );
            }
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

