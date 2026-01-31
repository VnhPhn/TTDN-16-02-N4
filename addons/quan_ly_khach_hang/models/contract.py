from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class Contract(models.Model):
    _name = 'contract'
    _description = 'Bảng chứa thông tin hợp đồng'

    contract_id = fields.Char("Mã hợp đồng", required=True)
    contract_name = fields.Char("Tên hợp đồng")
    customer_id = fields.Many2one('customer', string="Khách hàng", required=True, ondelete='cascade')
    start_date = fields.Date("Ngày bắt đầu hợp đồng", required=True)
    end_date = fields.Date("Ngày kết thúc hợp đồng", required=True)
    state = fields.Selection([
        ('active', 'Đang hoạt động'),
        ('ended', 'Đã kết thúc')
    ], string="Trạng thái hợp đồng", required=True)

    # Đặt tên hiển thị cho bản ghi
    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.contract_id}] {record.contract_name}"
            result.append((record.id, name))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super(Contract, self).create(vals_list)
        try:
            self.env['cskh_task'].create_from_contract(records)
        except Exception:
            pass
        try:
            self.env['sales_task'].create_from_contract(records)
        except Exception:
            pass
        # Award loyalty points for new contracts (default: 50 points per contract)
        try:
            for rec in records:
                try:
                    if rec.customer_id:
                        rec.customer_id.add_loyalty_points(50, reason=f'contract:create:{rec.contract_id}', user_id=self.env.uid)
                except Exception:
                    pass
        except Exception:
            pass
        return records

    def unlink(self):
        # Cancel any mirrored project tasks created from these contracts
        try:
            dept_models = ['sales_task', 'cskh_task', 'marketing_task', 'ky_thuat_task']
            for m in dept_models:
                try:
                    tasks = self.env[m].search([('source_model', '=', 'contract'), ('source_id', 'in', self.ids)])
                    if tasks:
                        pts = tasks.mapped('project_task_id')
                        if pts:
                            try:
                                pts.action_cancel()
                            except Exception:
                                pts.write({'state': 'cancel'})
                except Exception:
                    _logger.exception('Error while cancelling dept tasks for contract.unlink in model %s', m)
        except Exception:
            _logger.exception('Unexpected error while cancelling project tasks for contract.unlink')

        affected_customers = self.mapped('customer_id')
        # Count how many contracts per affected customer are being deleted in this unlink
        contract_counts = {}
        for cust in affected_customers:
            contract_counts[cust.id] = len(self.filtered(lambda r: r.customer_id and r.customer_id.id == cust.id))

        res = super(Contract, self).unlink()

        # Deduct loyalty points that were awarded on contract creation (default 50 per contract)
        for cust in affected_customers:
            try:
                deduct = contract_counts.get(cust.id, 0) * 50
                if deduct:
                    try:
                        cust.add_loyalty_points(-deduct, reason=f'contract:unlink:deduct_{deduct}', user_id=self.env.uid)
                    except Exception:
                        _logger.exception('Failed to deduct loyalty points for customer %s after contract unlink', cust.id)
                # Recompute tier to reflect changed totals
                try:
                    cust._compute_customer_tier()
                except Exception:
                    _logger.exception('Failed to recompute customer tier after contract unlink for %s', cust.id)
            except Exception:
                _logger.exception('Failed to update customer after contract unlink %s', cust.id)
        return res
