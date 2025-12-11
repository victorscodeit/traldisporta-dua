/** @odoo-module */
import { ListController } from "@web/views/list/list_controller";
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

export class ExpedienteListController extends ListController {
   setup() {
       super.setup();
   }
   
   onClickSubirFacturas() {
       this.actionService.doAction({
          type: 'ir.actions.act_window',
          res_model: 'aduanas.subir.facturas.wizard',
          name: 'Subir Facturas PDF',
          view_mode: 'form',
          view_type: 'form',
          views: [[false, 'form']],
          target: 'new',
          res_id: false,
      });
   }
}

registry.category("views").add("expediente_list_button", {
   ...listView,
   Controller: ExpedienteListController,
   buttonTemplate: "aduanas_transport.ListView.Buttons",
});

