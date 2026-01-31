from odoo import models, fields, api
from odoo.addons.quan_ly_khach_hang.services import ai_client # type: ignore

class Feedback(models.Model):
    _name = 'feedback'
    _description = 'Bảng chứa thông tin phản hồi'

    feedback_id = fields.Char("Mã phản hồi", required=True)
    feedback_name = fields.Char("Tên phản hồi")
    customer_id = fields.Many2one('customer', string="Khách hàng", required=True, ondelete='cascade')
    feedback = fields.Text("Nội dung phản hồi", required=True)
    feedback_date = fields.Datetime("Ngày phản hồi", required=True)
    rating = fields.Selection([
        ('1', '1 sao'),
        ('2', '2 sao'),
        ('3', '3 sao'),
        ('4', '4 sao'),
        ('5', '5 sao')
    ], string="Đánh giá", required=True)

    # AI sentiment analysis fields
    sentiment_label = fields.Selection([
        ('positive', 'Tích cực'),
        ('neutral', 'Trung tính'),
        ('negative', 'Tiêu cực'),
        ('unknown', 'Không xác định')
    ], string='Cảm xúc', default='unknown', copy=False)
    sentiment_score = fields.Float(string='Sentiment score', digits=(3, 2), copy=False)
    sentiment_explain = fields.Text(string='AI explanation', copy=False)
    sentiment_analyzed_date = fields.Datetime(string='Analyzed at', copy=False)

    # Đặt tên hiển thị cho bản ghi
    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.feedback_id}] {record.feedback_name}"
            result.append((record.id, name))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super(Feedback, self).create(vals_list)
        # Analyze sentiment first (may create CSKH tasks when negative)
        try:
            records.sudo().analyze_sentiment()
        except Exception:
            pass
        # Ensure department tasks are created (ky_thuat for low ratings, marketing)
        # Note: CSKH tasks are created inside analyze_sentiment() to avoid duplicates
        return records

    def analyze_sentiment(self):
        """Analyze sentiment for this feedback record using configured AI service."""
        for rec in self:
            text = (rec.feedback or '').strip()
            if not text:
                rec.write({'sentiment_label': 'unknown', 'sentiment_score': 0.0, 'sentiment_explain': 'No text'})
                continue
            try:
                # pass environment so ai_client can read ir.config_parameter
                result = ai_client.analyze_sentiment(text, env=self.env)
                # Post-process: override AI result when heuristics indicate clear negativity
                label = (result.get('label') or 'unknown').lower()
                score = float(result.get('score') or 0.0)
                explain = result.get('explain') or ''

                text_l = text.lower()
                negative_keywords = ['tệ', 'thất vọng', 'không hài', 'không hài lòng', 'hỏng', 'lỗi', 'chê', 'nhàm chán', 'dở', 'tệ hại', 'bực']
                positive_keywords = ['tốt', 'tuyệt', 'tích cực', 'hài lòng', 'tuyệt vời', 'yêu thích']

                # If text contains negative keywords, force negative
                if any(kw in text_l for kw in negative_keywords):
                    label = 'negative'
                    score = max(score, 0.85)
                    explain = (explain + ' | Overrode to negative by keyword heuristic').strip(' |')

                # If numeric rating indicates negative (1-2), prefer negative
                try:
                    if rec.rating and str(rec.rating) in ('1', '2'):
                        label = 'negative'
                        score = max(score, 0.6)
                        explain = (explain + ' | Overrode to negative by rating').strip(' |')
                except Exception:
                    pass

                rec.write({
                    'sentiment_label': label,
                    'sentiment_score': score,
                    'sentiment_explain': explain,
                    'sentiment_analyzed_date': fields.Datetime.now(),
                })
                # If final label is negative, auto-create a CSKH task (avoid duplicates)
                if label == 'negative':
                    try:
                        cskh = self.env['cskh_task'].sudo()
                        # check existing task for this feedback
                        existing = cskh.search([('source_model', '=', 'feedback'), ('source_id', '=', rec.id)], limit=1)
                        if not existing:
                            cskh.create_from_feedback([rec])
                    except Exception:
                        pass
            except Exception as e:
                rec.write({'sentiment_label': 'unknown', 'sentiment_score': 0.0, 'sentiment_explain': str(e)})

    # (create is implemented above; duplicate definition removed)

    def write(self, vals):
        # If only sentiment fields are being written, skip auto analysis
        skip_keys = {'sentiment_label', 'sentiment_score', 'sentiment_explain', 'sentiment_analyzed_date'}
        if set(vals.keys()).issubset(skip_keys):
            return super(Feedback, self).write(vals)
        res = super(Feedback, self).write(vals)
        try:
            self.sudo().analyze_sentiment()
        except Exception:
            pass
        return res
