# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.addons.quan_ly_khach_hang.services import ai_client


class FeedbackAIController(http.Controller):
	@http.route('/quan_ly_khach_hang/ai/feedback/analyze', type='json', auth='user', methods=['POST'])
	def analyze_feedback(self, feedback_id=None, **kw):
		"""Analyze a single feedback by id and store sentiment fields."""
		fid = feedback_id or kw.get('feedback_id')
		if not fid:
			return {'error': 'missing feedback_id'}
		try:
			fid = int(fid)
		except Exception:
			return {'error': 'invalid feedback_id'}
		fb = request.env['feedback'].sudo().browse(fid)
		if not fb.exists():
			return {'error': 'feedback not found'}
		# Use model helper which itself calls ai_client
		fb.sudo().analyze_sentiment()
		return {
			'id': fb.id,
			'sentiment_label': fb.sentiment_label,
			'sentiment_score': float(fb.sentiment_score or 0.0),
			'sentiment_explain': fb.sentiment_explain,
			'sentiment_analyzed_date': fb.sentiment_analyzed_date,
		}

	@http.route('/quan_ly_khach_hang/ai/feedback/batch', type='json', auth='user', methods=['POST'])
	def batch_analyze(self, limit=50, **kw):
		"""Batch analyze recent feedbacks that are not yet analyzed."""
		try:
			limit = int(kw.get('limit', limit))
		except Exception:
			limit = 50
		domain = [('sentiment_label', '=', 'unknown')]
		recs = request.env['feedback'].sudo().search(domain, limit=limit, order='feedback_date desc')
		processed = []
		for r in recs:
			try:
				r.analyze_sentiment()
				processed.append({'id': r.id, 'label': r.sentiment_label, 'score': float(r.sentiment_score or 0.0)})
			except Exception as e:
				processed.append({'id': r.id, 'error': str(e)})
		return {'processed': processed, 'count': len(processed)}

