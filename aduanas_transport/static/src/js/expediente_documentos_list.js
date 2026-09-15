/** @odoo-module **/
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { _t } from "@web/core/l10n/translation";

export class ExpedienteDocumentosListController extends ListController {
    async onClickSubirDocumento() {
        const ctx = this.props.context || {};
        const expedienteId = ctx.default_res_id;
        await this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "ir.attachment",
                name: _t("Subir documento"),
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_res_model: ctx.default_res_model || "aduana.expediente",
                    default_res_id: expedienteId || false,
                    default_type: "binary",
                    default_name: _t("Documento"),
                },
            },
            {
                onClose: async () => {
                    if (expedienteId) {
                        const action = await this.orm.call(
                            "aduana.expediente",
                            "action_view_documentos",
                            [[expedienteId]]
                        );
                        this.actionService.doAction(action, {
                            stackPosition: "replaceCurrentAction",
                        });
                    } else {
                        this.model.load();
                    }
                },
            }
        );
    }
}

registry.category("views").add("expediente_documentos_list", {
    ...listView,
    Controller: ExpedienteDocumentosListController,
    buttonTemplate: "aduanas_transport.DocumentosListView.Buttons",
});
