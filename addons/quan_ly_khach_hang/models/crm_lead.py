from odoo import models, fields, api

class CrmLead(models.Model):
    _name = 'crm_lead'
    _description = 'Bảng chứa thông tin cơ hội'

    crm_lead_id = fields.Char("Mã cơ hội", required=True)
    crm_lead_name = fields.Char("Tên cơ hội")
    stage_id = fields.Many2one('crm_stage', string="Giai đoạn")
    customer_id = fields.Many2one('customer', string="Khách hàng")
    probability = fields.Float("Xác suất thành công (%)", compute='_compute_probability', store=True)
    expected_revenue = fields.Float("Doanh thu dự kiến")

    @api.depends('stage_id')
    def _compute_probability(self):
        for record in self:
            if record.stage_id:
                record.probability = record.stage_id.probability

    @api.model_create_multi
    def create(self, vals_list):
        records = super(CrmLead, self).create(vals_list)
        # Tạo công việc CSKH từ cơ hội vừa tạo (nếu có khách hàng liên kết)
        try:
            self.env['cskh_task'].create_from_lead(records)
        except Exception:
            pass
        # Tạo công việc Sales từ cơ hội
        try:
            self.env['sales_task'].create_from_lead(records)
        except Exception:
            pass
        return records
