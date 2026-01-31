from odoo import models, fields, api

class CrmStage(models.Model):
    _name = 'crm_stage'
    _description = 'Giai đoạn Cơ hội'

    name = fields.Char("Tên giai đoạn", required=True)
    sequence = fields.Integer("Thứ tự")
    fold = fields.Boolean("Gập lại", help="Ẩn các giai đoạn này trong cột mặc định")
    probability = fields.Float("Xác suất (%)", help="Xác suất thành công của cơ hội ở giai đoạn này")

    # Tạo các giai đoạn mặc định
    @api.model
    def _create_default_stages(self):
        stages = [
            {'name': 'Mới', 'sequence': 1, 'fold': False, 'probability': 10.0},
            {'name': 'Đang xử lý', 'sequence': 2, 'fold': False, 'probability': 50.0},
            {'name': 'Đã đóng', 'sequence': 3, 'fold': True, 'probability': 100.0},
        ]
        for stage in stages:
            self.env['crm_stage'].create(stage)

    # Gọi phương thức tạo các giai đoạn mặc định khi module được khởi tạo
    def init(self):
        self._create_default_stages()
