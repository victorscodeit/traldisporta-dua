# -*- coding: utf-8 -*-
"""Generación XML G4Dec (forma F2: MC + MI) según G4DecV1Ent.xsd."""
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError
from xml.sax.saxutils import escape as xml_escape

NS_G4_ENT = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aduanas/"
    "es/aeat/adds/jdit/g4/ws/G4DecV1Ent.xsd"
)
G4_DEC_DEFAULT_ENDPOINT = "https://prewww1.aeat.es/wlpl/ADDS-JDIT/ws/G4DecV1SOAP"


class AduanasG4XmlBuilder(models.AbstractModel):
    _name = "aduanas.g4.xml.builder"
    _description = "Constructor XML G4 depósito temporal (G4DecV1)"

    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    def _g4_param(self, key, default=""):
        return (self._icp().get_param(key) or default).strip()

    def _is_preproduction(self, endpoint_url=None):
        if endpoint_url:
            return "prewww" in (endpoint_url or "").lower()
        return self._g4_param(
            "aduanas_transport.endpoint.g4_dec", G4_DEC_DEFAULT_ENDPOINT
        ).lower().find("prewww") >= 0

    def _recipient(self, endpoint_url):
        return "PRE.AEAT" if self._is_preproduction(endpoint_url) else "ES.AEAT"

    def _sender_id(self, expediente):
        icp = self._icp()
        forced = (icp.get_param("aduanas_transport.aeat_nif_firmante") or "").strip()
        if forced:
            return forced.replace(" ", "").replace("-", "").upper()[:17]
        company = expediente.env.company
        declarant_id = expediente._imp_eori(company.partner_id, "ES")
        if declarant_id and len(declarant_id) >= 9:
            return declarant_id[:17]
        vat = ((company.vat or "") or "").replace(" ", "").replace("-", "").upper()
        if len(vat) >= 9:
            return vat[:17]
        raise UserError(
            _("Configure el NIF/EORI del declarante (empresa) o «NIF firmante AEAT» para G4.")
        )

    def _supervising_office(self, expediente, endpoint_url):
        custom = self._g4_param("aduanas_transport.g4_supervising_office")
        if custom:
            office = custom.upper().replace(" ", "")
        else:
            office, _note = expediente._get_cc415a_office_code()
        if len(office) != 8 or not office.startswith("ES"):
            raise UserError(
                _("Oficina aduanera G4 inválida (%s). Debe ser código COL de 8 caracteres (ej. ES002501).")
                % office
            )
        return office

    def _estimated_arrival(self, expediente):
        dt = expediente.fecha_prevista or expediente.fecha_entrada_real
        if not dt:
            dt = fields.Datetime.now() + timedelta(days=1)
        return fields.Datetime.to_string(dt)[:19]

    def _lrn(self, g4_rec, expediente):
        raw = (g4_rec.lrn or "").strip()
        if not raw:
            base = (expediente.name or "G4%s" % expediente.id).replace(" ", "")
            raw = "G4-%s" % base
        return raw[:22]

    def _g4_full_address_xml(self, partner, default_country="ES"):
        if not partner:
            return ""
        street = " ".join(p for p in [partner.street or "", partner.street2 or ""] if p)[:70]
        city = (partner.city or "SIN CIUDAD")[:35]
        country = (
            partner.country_id.code if partner.country_id else default_country
        ) or default_country
        if not street:
            street = city or "S/N"
        return """<FullAddress>
<Street>%s</Street>
<Number>%s</Number>
<Country>%s</Country>
<PostCode>%s</PostCode>
<City>%s</City>
</FullAddress>""" % (
            xml_escape(street),
            xml_escape("S/N"),
            xml_escape(country[:2]),
            xml_escape((partner.zip or "00000")[:17]),
            xml_escape(city),
        )

    def _g4_communication_xml(self, partner):
        email = (partner.email or "").strip()[:512]
        if not email:
            return ""
        return """<Communication>
<CommType>EM</CommType>
<CommId>%s</CommId>
</Communication>""" % xml_escape(email)

    def _g4_declarant_xml(self, expediente):
        company = expediente.env.company
        partner = company.partner_id
        decl_id = expediente._imp_eori(partner, "ES")
        if decl_id != "ESB65496556":
            raise UserError(_("Declarant G4: se requiere ESB65496556 (revise NIF de la compañía)."))
        name = (partner.name or company.name or "Declarante")[:70]
        addr = self._g4_full_address_xml(partner, "ES")
        comm = self._g4_communication_xml(partner)
        comm_block = ("\n%s" % comm) if comm else ""
        return """<Declarant>
<Id>%s</Id>
<Name>%s</Name>
%s%s
</Declarant>""" % (xml_escape(decl_id), xml_escape(name), addr, comm_block)

    def _g4_actor_block(self, tag, partner, expediente, default_country, type_of_person="2"):
        if not partner:
            return ""
        ident = expediente._imp_eori(partner, default_country)
        id_xml = ""
        if ident and len(ident) >= 9:
            if ident.startswith("ES") or self._g4_param(
                "aduanas_transport.g4_allow_foreign_actor_id", ""
            ).lower() in ("1", "true", "yes", "si", "sí"):
                id_xml = "<Id>%s</Id>" % xml_escape(ident[:17])
        name = (partner.name or tag)[:70]
        addr = self._g4_full_address_xml(partner, default_country)
        comm = self._g4_communication_xml(partner)
        comm_block = ("\n%s" % comm) if comm else ""
        return """<%s>
%s
<TypeOfPerson>%s</TypeOfPerson>
<Name>%s</Name>
%s%s
</%s>""" % (
            tag,
            id_xml,
            type_of_person,
            xml_escape(name),
            addr,
            comm_block,
            tag,
        )

    def _location_of_goods_xml(self, expediente, office):
        icp = self._icp()
        loc_type = self._g4_param("aduanas_transport.g4_loc_type", "B")
        loc_qual = self._g4_param("aduanas_transport.g4_loc_qualifier", "Y")
        loc_ref = self._g4_param("aduanas_transport.g4_loc_customs_ref") or (
            "%sAAAAAA" % office[:8]
        )
        loc_add = self._g4_param("aduanas_transport.g4_loc_add_id")
        loc_add_xml = (
            "<LocAddId>%s</LocAddId>" % xml_escape(loc_add[:8]) if loc_add else ""
        )
        wh_type = self._g4_param("aduanas_transport.g4_warehouse_type", "V")
        wh_id = (
            self._g4_param("aduanas_transport.g4_warehouse_id")
            or expediente.location_authorisation_number
            or icp.get_param("aduanas_transport.aeat_preprod_location_authorisation")
            or "010101DA11"
        )
        return """<LocationOfGoods>
<LocType>%s</LocType>
<LocQualifier>%s</LocQualifier>
<LocCoded>
<LocCustomsOffice>
<Reference>%s</Reference>
</LocCustomsOffice>
%s
</LocCoded>
</LocationOfGoods>
<Warehouse>
<WarehouseType>%s</WarehouseType>
<WarehouseId>%s</WarehouseId>
</Warehouse>""" % (
            xml_escape(loc_type[:1]),
            xml_escape(loc_qual[:1]),
            xml_escape(loc_ref[:17]),
            loc_add_xml,
            xml_escape(wh_type[:1]),
            xml_escape(wh_id[:35]),
        )

    def _transport_document_xml(self, expediente):
        doc_type = self._g4_param("aduanas_transport.g4_transport_doc_type", "N704")
        ref = (
            (expediente.numero_albaran_remitente or "").strip()
            or (expediente.numero_factura or "").strip()
            or (expediente.name or "").strip()
        )
        if not ref:
            ref = "REF%s" % (expediente.id or 0)
        return """<TransportDocument>
<TransDocType>%s</TransDocType>
<TransDocRef>%s</TransDocRef>
</TransportDocument>""" % (
            xml_escape(doc_type[:4]),
            xml_escape(ref[:70]),
        )

    def _arrival_transport_xml(self, expediente):
        means_type = self._g4_param("aduanas_transport.g4_arrival_transport_type", "30")
        means_id = (
            (expediente.matricula or "").strip()
            or (expediente.codigo_transporte or "").strip()
            or ("LKW52" if self._is_preproduction() else "TRANSPORT")
        )
        return """<ArrivalTransportMeans>
<TransportMeansType>%s</TransportMeansType>
<TransportMeansId>%s</TransportMeansId>
</ArrivalTransportMeans>""" % (
            xml_escape(means_type[:2]),
            xml_escape(means_id[:35]),
        )

    def _master_items_xml(self, expediente):
        blocks = []
        for idx, line in enumerate(
            expediente.line_ids.sorted(key=lambda l: l.item_number or l.id or 0), 1
        ):
            partida = (line.taric_completo or line.partida or "").replace(" ", "").replace(".", "")
            if len(partida) < 6 or not partida[:6].isdigit():
                raise UserError(
                    _("Línea %s: informe código arancelario (mín. 6 dígitos HS) para G4.")
                    % idx
                )
            hs = partida[:6]
            cn = partida[6:8] if len(partida) >= 8 else ""
            cn_xml = (
                "<CombinedNomenclature>%s</CombinedNomenclature>" % xml_escape(cn)
                if cn
                else ""
            )
            desc = (line.descripcion or "Mercancía")[:512]
            gross = line.peso_bruto or 0.0
            if gross <= 0:
                raise UserError(_("Línea %s: indique peso bruto para G4.") % idx)
            pkg_type = (line.type_of_packages or "CT").strip().upper()[:2]
            pkg_count = int(line.bultos or 1)
            gin = line.item_number or idx
            blocks.append(
                """<MI_MasterConsignment_Item>
<GoodsItemNumber>%s</GoodsItemNumber>
<Commodity>
<CommodityCode>
<HarmonizedSystem>%s</HarmonizedSystem>
%s
</CommodityCode>
<DescriptionOfGoods>%s</DescriptionOfGoods>
</Commodity>
<GrossMass>%.6f</GrossMass>
<Packaging>
<PackagingType>%s</PackagingType>
<NumberOfPackages>%s</NumberOfPackages>
</Packaging>
</MI_MasterConsignment_Item>"""
                % (
                    gin,
                    xml_escape(hs),
                    cn_xml,
                    xml_escape(desc),
                    gross,
                    xml_escape(pkg_type),
                    pkg_count,
                )
            )
        return "\n".join(blocks)

    def validate_g4_expediente(self, g4_rec):
        expediente = g4_rec.expediente_id
        expediente.ensure_one()
        if expediente.direction != "import":
            raise UserError(_("G4 solo aplica a expedientes de importación."))
        if not expediente.line_ids:
            raise UserError(_("Añada al menos una línea de mercancía al expediente."))
        if not expediente.consignatario:
            raise UserError(_("Indique el consignatario (destinatario) en el expediente."))
        if not expediente.remitente:
            raise UserError(_("Indique el remitente en el expediente."))
        expediente._validate_import_cc415a_roles()
        return expediente

    def build_g4_body(self, g4_rec, endpoint_url=None):
        """Cuerpo G4DecV1Ent (MES_Message + DEC_Declaration), sin sobre SOAP."""
        self.validate_g4_expediente(g4_rec)
        expediente = g4_rec.expediente_id
        endpoint_url = endpoint_url or self._g4_param(
            "aduanas_transport.endpoint.g4_dec", G4_DEC_DEFAULT_ENDPOINT
        )
        now = fields.Datetime.now()
        prep_time = now.strftime("%Y-%m-%dT%H:%M:%S")
        msg_id = ("%s-G4-%s" % (self._lrn(g4_rec, expediente), now.strftime("%Y%m%d%H%M%S")))[:40]
        sender = self._sender_id(expediente)
        recipient = self._recipient(endpoint_url)
        test_xml = (
            "<TestIndicator>S</TestIndicator>"
            if self._is_preproduction(endpoint_url)
            else ""
        )
        office = self._supervising_office(expediente, endpoint_url)
        lrn = self._lrn(g4_rec, expediente)
        total_gross = sum((l.peso_bruto or 0.0) for l in expediente.line_ids) or 0.0

        consignor = self._g4_actor_block(
            "Consignor", expediente.remitente, expediente, expediente.pais_origen or "AD", "2"
        )
        consignee = self._g4_actor_block(
            "Consignee", expediente.consignatario, expediente, "ES", "2"
        )
        dest_country = (expediente.pais_destino or "ES").strip().upper()[:2]

        loc_wh = self._location_of_goods_xml(expediente, office)
        mc_block = """<MC_MasterConsignment>
%s
%s
%s
%s
<TotalGrossMass>%.6f</TotalGrossMass>
%s
%s
<DestinationCountry>%s</DestinationCountry>
%s
</MC_MasterConsignment>""" % (
            self._transport_document_xml(expediente),
            self._arrival_transport_xml(expediente),
            loc_wh,
            total_gross,
            consignor,
            consignee,
            xml_escape(dest_country),
            self._master_items_xml(expediente),
        )

        return """<MES_Message>
<Sender>%s</Sender>
<Recipient>%s</Recipient>
<MessageId>%s</MessageId>
<PreparationDateAndTime>%s</PreparationDateAndTime>
%s
</MES_Message>
<DEC_Declaration>
<LRN>%s</LRN>
<SupervisingCustomsOffice>%s</SupervisingCustomsOffice>
<EstimatedDateAndTimeOfArrival>%s</EstimatedDateAndTimeOfArrival>
%s
%s
</DEC_Declaration>""" % (
            xml_escape(sender),
            xml_escape(recipient),
            xml_escape(msg_id),
            prep_time,
            test_xml,
            xml_escape(lrn),
            xml_escape(office),
            self._estimated_arrival(expediente),
            self._g4_declarant_xml(expediente),
            mc_block,
        )

    def build_g4_soap_envelope(self, g4_rec, endpoint_url=None):
        body = self.build_g4_body(g4_rec, endpoint_url=endpoint_url)
        return """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:g4="%s">
<soapenv:Header/>
<soapenv:Body>
<g4:G4DecV1Ent>
%s
</g4:G4DecV1Ent>
</soapenv:Body>
</soapenv:Envelope>""" % (NS_G4_ENT, body)
