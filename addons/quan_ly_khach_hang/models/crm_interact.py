from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class CrmInteract(models.Model):
    _name = 'crm_interact'
    _description = 'Bảng chứa thông tin tương tác'

    crm_interact_id = fields.Char("Mã tương tác", required=True)
    crm_interact_name = fields.Char("Tên tương tác")
    customer_id = fields.Many2one('customer', string="Khách hàng", required=True, ondelete='cascade')
    interaction_type = fields.Selection([
        ('call', 'Cuộc gọi'),
        ('email', 'Email'),
        ('meeting', 'Meeting')
    ], string="Loại tương tác", required=True)
    date = fields.Datetime("Ngày tương tác", required=True)
    note = fields.Text("Ghi chú về tương tác")

    # Đặt tên hiển thị cho bản ghi
    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.crm_interact_id}] {record.crm_interact_name}"
            result.append((record.id, name))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super(CrmInteract, self).create(vals_list)
        try:
            self.env['cskh_task'].create_from_interact(records)
        except Exception:
            pass
        # marketing task
        try:
            self.env['marketing_task'].create_from_interact(records)
        except Exception:
            pass
        # Auto-award loyalty points based on interaction type
        try:
            points_map = {
                'meeting': 10,
                'call': 2,
                'email': 1,
            }
            for rec in records:
                try:
                    if rec.customer_id and rec.interaction_type in points_map:
                        pts = points_map.get(rec.interaction_type, 0)
                        if pts:
                            rec.customer_id.add_loyalty_points(pts, reason=f'interaction:{rec.interaction_type}', user_id=self.env.uid)
                except Exception:
                    _logger.exception('Failed to award loyalty points for interact %s', rec.id)
        except Exception:
            _logger.exception('Error while awarding loyalty points after crm_interact.create')
        return records

    def unlink(self):
        # Cancel any mirrored project tasks created from these interactions
        try:
            dept_models = ['cskh_task', 'marketing_task', 'sales_task', 'ky_thuat_task']
            for m in dept_models:
                try:
                    tasks = self.env[m].search([('source_model', '=', 'crm_interact'), ('source_id', 'in', self.ids)])
                    if tasks:
                        pts = tasks.mapped('project_task_id')
                        if pts:
                            try:
                                pts.action_cancel()
                            except Exception:
                                pts.write({'state': 'cancel'})
                except Exception:
                    _logger.exception('Error while cancelling dept tasks for crm_interact.unlink in model %s', m)
        except Exception:
            _logger.exception('Unexpected error while cancelling project tasks for crm_interact.unlink')

        affected_customers = self.mapped('customer_id')
        res = super(CrmInteract, self).unlink()
        for cust in affected_customers:
            try:
                cust.recompute_loyalty_points()
                cust._compute_customer_tier()
            except Exception:
                _logger.exception('Failed to update customer after crm_interact unlink %s', cust.id)
        return res
