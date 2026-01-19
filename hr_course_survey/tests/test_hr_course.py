# Copyright 2019 Creu Blanca
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.addons.base.tests.common import BaseCommon


class TestHrCourse(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Disable tracking
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        # Create survey manager user with necessary groups
        group_survey_manager = cls.env.ref('survey.group_survey_manager')
        group_user = cls.env.ref('base.group_user')
        cls.survey_manager = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Survey Manager',
            'login': 'survey_manager',
            'email': 'survey.manager@example.com',
            'groups_id': [(6, 0, [group_survey_manager.id, group_user.id])],
        })
        
        # Create survey
        cls.survey = cls.env["survey.survey"].with_user(cls.survey_manager).create({
            "title": "Test Survey",
            "access_mode": "public",
            "users_login_required": True,
            "users_can_go_back": False,
            "scoring_type": "scoring_without_answers",
        })
        
        # Create a page and question
        cls.page_0 = cls.env['survey.question'].create({
            'title': 'First page',
            'sequence': 1,
            'is_page': True,
            'survey_id': cls.survey.id,
        })
        
        cls.question = cls.env['survey.question'].create({
            'title': 'Q0',
            'question_type': 'simple_choice',
            'survey_id': cls.survey.id,
            'page_id': cls.page_0.id,
            'suggested_answer_ids': [
                (0, 0, {"value": "Choice0", "is_correct": True, "answer_score": 100}),
                (0, 0, {"value": "Choice1"}),
            ]
        })
        
        cls.course_categ = cls.env["hr.course.category"].create({"name": "Category1"})
        cls.employee1 = cls.env["hr.employee"].create({"name": "Employee1"})
        cls.employee2 = cls.env["hr.employee"].create(
            {"name": "Employee2", "user_id": cls.survey_manager.id}
        )
        cls.course = cls.env["hr.course"].create(
            {
                "name": "Test Course",
                "category_id": cls.course_categ.id,
                "examination_survey_id": cls.survey.id,
                "permanence": False,
            }
        )
    
    def _add_answer_line(cls, question, answer, answer_id, answer_type, answer_fname):
        return cls.env['survey.user_input.line'].create({
            'user_input_id': answer.id,
            'question_id': question.id,
            answer_fname: answer_id,
            'answer_type': answer_type,
        })

    def test_hr_schedule(cls):
        cls.course_schedule = cls.env["hr.course.schedule"].create(
            {
                "name": "Test Schedule",
                "course_id": cls.course.id,
                "cost": 100,
                "examination_survey_id": cls.survey.id,
                "authorized_by": cls.employee1.id,
                "start_date": "2019-02-15",
                "end_date": "2019-02-20",
            }
        )
        with cls.assertRaises(ValidationError):
            cls.course_schedule.write({"end_date": "2019-02-10"})

        cls.assertEqual(cls.course_schedule.state, "draft")
        cls.course_schedule.cancel_course()
        cls.assertEqual(cls.course_schedule.state, "cancelled")
        cls.course_schedule.back2draft()

        cls.course_schedule.draft2waiting()
        cls.assertEqual(cls.course_schedule.state, "waiting_attendees")

        cls.course_schedule.attendant_ids = [
            (6, 0, [cls.employee1.id, cls.employee2.id])
        ]
        cls.assertTrue(cls.course_schedule.attendant_ids)
        cls.assertEqual(len(cls.course_schedule.attendant_ids), 2)

        cls.course_schedule.waiting2inprogress()
        cls.assertEqual(cls.course_schedule.state, "in_progress")
        cls.assertEqual(len(cls.course_schedule.course_attendee_ids), 2)
        cls.assertFalse(cls.course_schedule.course_attendee_ids[0].survey_answer_id)
        cls.course_schedule.attendant_ids = [(3, cls.employee2.id, 0)]
        cls.course_schedule.waiting2inprogress()
        cls.assertEqual(len(cls.course_schedule.attendant_ids), 1)
        cls.assertEqual(len(cls.course_schedule.course_attendee_ids), 1)
        cls.employee1._compute_count_courses()
        cls.assertEqual(cls.employee1.count_courses, 1)
        cls.employee1.action_view_course()

        cls.course_schedule.inprogress2validation()
        cls.assertEqual(cls.course_schedule.state, "in_validation")
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "pending")
        with cls.assertRaises(ValidationError):
            cls.course_schedule.course_attendee_ids.resend_survey()
        answer = cls.course_schedule.course_attendee_ids.survey_answer_id
        cls.assertTrue(answer.hr_course_attendee_ids)
        cls._add_answer_line(
            cls.question,
            answer,
            cls.question.suggested_answer_ids.filtered(
                lambda l: l.value == "Choice1"
            ).id,
            answer_type="suggestion",
            answer_fname="suggested_answer_id",
        )
        answer._mark_done()
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "failed")
        cls.course_schedule.course_attendee_ids.resend_survey()
        cls.assertNotEqual(
            answer, cls.course_schedule.course_attendee_ids.survey_answer_id
        )
        answer = cls.course_schedule.course_attendee_ids.survey_answer_id
        cls.assertTrue(answer.hr_course_attendee_ids)
        cls._add_answer_line(
            cls.question,
            answer,
            cls.question.suggested_answer_ids.filtered(
                lambda l: l.value == "Choice0"
            ).id,
            answer_type="suggestion",
            answer_fname="suggested_answer_id",
        )
        answer._mark_done()
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "passed")
        with cls.assertRaises(ValidationError):
            cls.course_schedule.course_attendee_ids.resend_survey()

        cls.course_schedule.attendant_ids = [(6, 0, [cls.employee2.id])]
        cls.course_schedule.waiting2inprogress()
        cls.assertEqual(len(cls.course_schedule.attendant_ids), 1)
        cls.assertEqual(len(cls.course_schedule.course_attendee_ids), 1)
        cls.employee2._compute_count_courses()
        cls.assertEqual(cls.employee2.count_courses, 1)
        cls.employee2.action_view_course()

        cls.course_schedule.inprogress2validation()
        cls.assertEqual(cls.course_schedule.state, "in_validation")
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "pending")
        with cls.assertRaises(ValidationError):
            cls.course_schedule.course_attendee_ids.resend_survey()
        answer = cls.course_schedule.course_attendee_ids.survey_answer_id
        cls.assertTrue(answer.hr_course_attendee_ids)
        cls._add_answer_line(
            cls.question,
            answer,
            cls.question.suggested_answer_ids.filtered(
                lambda l: l.value == "Choice1"
            ).id,
            answer_type="suggestion",
            answer_fname="suggested_answer_id",
        )
        answer._mark_done()
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "failed")
        cls.course_schedule.course_attendee_ids.resend_survey()
        cls.assertNotEqual(
            answer, cls.course_schedule.course_attendee_ids.survey_answer_id
        )
        answer = cls.course_schedule.course_attendee_ids.survey_answer_id
        cls.assertTrue(answer.hr_course_attendee_ids)
        cls._add_answer_line(
            cls.question,
            answer,
            cls.question.suggested_answer_ids.filtered(
                lambda l: l.value == "Choice0"
            ).id,
            answer_type="suggestion",
            answer_fname="suggested_answer_id",
        )
        answer._mark_done()
        cls.assertEqual(cls.course_schedule.course_attendee_ids.result, "passed")
        with cls.assertRaises(ValidationError):
            cls.course_schedule.course_attendee_ids.resend_survey()
