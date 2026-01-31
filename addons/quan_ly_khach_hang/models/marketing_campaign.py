from odoo import models, fields, api

class MarketingCampaign(models.Model):
    _name = 'marketing_campaign'
    _description = 'Bảng chứa thông tin chiến lược marketing'

    marketing_campaign_id = fields.Char("Mã chiến lược marketing", required=True)
    marketing_campaign_name = fields.Char("Tên chiến lược marketing", required=True)
    start_date = fields.Date("Ngày bắt đầu", required=True)
    end_date = fields.Date("Ngày kết thúc", required=True)
    customer_ids = fields.Many2many('customer', string="Khách hàng tham gia")

    # Đặt tên hiển thị cho bản ghi
    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.marketing_campaign_id}] {record.marketing_campaign_name}"
            result.append((record.id, name))
        return result
