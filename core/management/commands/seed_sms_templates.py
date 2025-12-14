from django.core.management.base import BaseCommand
from core.models import OrgSMSTemplate, Organization

class Command(BaseCommand):
    help = 'Seed the database with pre-built SMS templates for organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org-slug',
            type=str,
            help='Specific organization slug to seed templates for (default: all organizations)',
        )
        parser.add_argument(
            '--create-demo-org',
            action='store_true',
            help='Create a demo organization if none exist',
        )

    def handle(self, *args, **options):
        # Get organizations to seed
        if options['org_slug']:
            try:
                organizations = [Organization.objects.get(slug=options['org_slug'])]
            except Organization.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Organization with slug "{options["org_slug"]}" not found')
                )
                return
        else:
            organizations = Organization.objects.filter(is_active=True)
            if not organizations.exists():
                if options['create_demo_org']:
                    # Create a demo organization
                    org = Organization.objects.create(
                        name='Demo School',
                        slug='demo-school',
                        org_type='other',
                        approval_status='approved',
                        is_active=True,
                        onboarded=True,
                    )
                    organizations = [org]
                    self.stdout.write(
                        self.style.SUCCESS(f'Created demo organization: {org.name}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING('No active organizations found. Use --create-demo-org to create one.')
                    )
                    return

        # Template categories and content
        template_categories = {
            'School Announcements': [
                {
                    'name': 'School Closure',
                    'content': 'Dear parents, {school_name} will be closed tomorrow due to {reason}. Classes will resume on {date}. Thank you for your understanding.'
                },
                {
                    'name': 'Early Dismissal',
                    'content': 'Attention parents: Students will be dismissed early today at {time} due to {reason}. Please ensure someone is available to pick up your child.'
                },
                {
                    'name': 'Holiday Notice',
                    'content': 'Happy Holidays! {school_name} will be closed from {start_date} to {end_date} for {holiday_name}. We look forward to seeing you all soon!'
                },
                {
                    'name': 'Weather Delay',
                    'content': 'Due to weather conditions, school will open {delay_hours} hour(s) late today. Regular dismissal time remains unchanged.'
                },
                {
                    'name': 'PTA Meeting',
                    'content': 'Reminder: PTA meeting scheduled for {date} at {time} in the school auditorium. Your participation is important for our students\' future.'
                },
                {
                    'name': 'Sports Event',
                    'content': 'Exciting news! Our {team_sport} team will play against {opponent} on {date} at {time}. Come support our champions!'
                },
                {
                    'name': 'Exam Schedule',
                    'content': 'Final exams begin {start_date}. Study hard! Report to your assigned exam rooms by {time}. Good luck to all students!'
                },
                {
                    'name': 'Report Card Distribution',
                    'content': 'Report cards for {term} are ready for collection from {date}. Please collect them from the school office during working hours.'
                },
            ],
            'Payment Reminders': [
                {
                    'name': 'School Fees Due',
                    'content': 'Reminder: School fees for {month} are due by {due_date}. Amount: GHS {amount}. Late payments may incur penalties. Contact accounts office for assistance.'
                },
                {
                    'name': 'Outstanding Balance',
                    'content': 'Your account shows an outstanding balance of GHS {amount}. Please settle this payment to avoid service interruption. Contact: {contact_number}'
                },
                {
                    'name': 'Payment Confirmation',
                    'content': 'Payment received: GHS {amount} for {description}. Thank you! Your new balance is GHS {balance}. Receipt #{receipt_number}'
                },
                {
                    'name': 'Partial Payment',
                    'content': 'Thank you for your payment of GHS {paid_amount}. Outstanding balance: GHS {remaining_amount}. Please complete payment by {due_date}.'
                },
                {
                    'name': 'Scholarship Awarded',
                    'content': 'Congratulations! {student_name} has been awarded a {scholarship_name} scholarship covering {percentage}% of school fees. Contact administration for details.'
                },
                {
                    'name': 'Payment Plan Available',
                    'content': 'Payment difficulties? We offer flexible payment plans. Contact our accounts office to discuss options and avoid penalties.'
                },
            ],
            'Emergency Alerts': [
                {
                    'name': 'Medical Emergency',
                    'content': 'URGENT: {student_name} has been taken to {hospital_name} due to {condition}. Please contact the school immediately at {contact_number}.'
                },
                {
                    'name': 'Security Alert',
                    'content': 'SECURITY ALERT: Please ensure all students are accounted for. {description}. Follow school safety protocols. Contact: {emergency_contact}'
                },
                {
                    'name': 'Bus Delay',
                    'content': 'School bus #{bus_number} is delayed due to {reason}. Expected arrival time: {new_time}. Students should remain in designated waiting areas.'
                },
                {
                    'name': 'Lost Child',
                    'content': 'ATTENTION: {child_name} (age {age}) is missing from school premises. If found, please bring to the main office immediately. Description: {description}'
                },
                {
                    'name': 'Fire Drill',
                    'content': 'FIRE DRILL in progress. All students and staff must evacuate the building immediately following established procedures. This is not a real emergency.'
                },
                {
                    'name': 'Health Advisory',
                    'content': 'Health Advisory: Cases of {illness} reported. Please monitor your child for symptoms: {symptoms}. Contact school nurse if concerned.'
                },
            ],
            'Academic Notices': [
                {
                    'name': 'Assignment Due',
                    'content': '{subject} assignment "{title}" is due on {due_date}. Please ensure it is submitted on time to avoid penalties. Late submissions accepted until {late_date}.'
                },
                {
                    'name': 'Grade Improvement',
                    'content': 'Congratulations {student_name}! Your {subject} grade has improved from {old_grade} to {new_grade}. Keep up the excellent work!'
                },
                {
                    'name': 'Parent-Teacher Conference',
                    'content': 'Parent-Teacher conference scheduled for {date} at {time}. Please meet with {teacher_name} to discuss {student_name}\'s progress. Room: {room_number}'
                },
                {
                    'name': 'Academic Achievement',
                    'content': 'Celebrating Excellence! {student_name} achieved {achievement} in {subject}. Position: {position}. Congratulations from the entire school community!'
                },
                {
                    'name': 'Study Group',
                    'content': 'Study group for {subject} struggling students will be held {day} at {time} in {location}. Additional help available - don\'t hesitate to attend!'
                },
                {
                    'name': 'Library Books Due',
                    'content': 'Library books borrowed by {student_name} are due today. Please return them to avoid fines. Overdue: {overdue_books}'
                },
            ],
            'Events & Activities': [
                {
                    'name': 'School Trip',
                    'content': 'Exciting School Trip! Destination: {destination}. Date: {date}. Cost: GHS {cost}. Permission slips due by {deadline}. Limited spaces available!'
                },
                {
                    'name': 'Cultural Event',
                    'content': 'Join us for {event_name} on {date} at {time}. Celebrate our cultural diversity! All parents and students welcome. Free entry.'
                },
                {
                    'name': 'Career Day',
                    'content': 'Career Day {date}: Meet professionals from various fields! Students can explore future career options. Register by {registration_deadline}.'
                },
                {
                    'name': 'Science Fair',
                    'content': 'Science Fair entries now open! Theme: {theme}. Submission deadline: {deadline}. Prizes for winners! Contact: {contact_teacher}'
                },
                {
                    'name': 'Graduation Ceremony',
                    'content': 'Graduation Ceremony for Class of {year} will be held on {date} at {time} in the school auditorium. Proud parents, save the date!'
                },
                {
                    'name': 'Community Service',
                    'content': 'Community Service Opportunity: {activity} on {date} at {location}. Help make a difference! Sign up in the school office by {deadline}.'
                },
            ],
            'Attendance & Discipline': [
                {
                    'name': 'Absentee Notice',
                    'content': '{student_name} was absent from school today without notification. Please provide a written excuse or contact the school. Repeated absences may affect grades.'
                },
                {
                    'name': 'Tardy Warning',
                    'content': '{student_name} arrived late to school today. School starts at {start_time}. Please ensure timely arrival to avoid disciplinary action.'
                },
                {
                    'name': 'Behavior Concern',
                    'content': 'We need to discuss {student_name}\'s recent behavior: {description}. Please schedule a meeting with {teacher_name} at your earliest convenience.'
                },
                {
                    'name': 'Positive Behavior',
                    'content': 'Great job {student_name}! Recognized for {positive_behavior} today. Your good conduct makes our school community proud. Keep it up!'
                },
                {
                    'name': 'Uniform Violation',
                    'content': '{student_name} reported for uniform violation: {violation}. Please ensure proper uniform tomorrow. Repeated violations may result in detention.'
                },
                {
                    'name': 'Attendance Award',
                    'content': 'Perfect Attendance Award! {student_name} has maintained 100% attendance for {period}. Congratulations! Certificate available in the office.'
                },
            ],
            'Health & Wellness': [
                {
                    'name': 'Vaccination Reminder',
                    'content': 'Vaccination Reminder: {vaccination_name} due for {student_name}. Please schedule appointment and bring vaccination card. Required for school attendance.'
                },
                {
                    'name': 'Dental Check-up',
                    'content': 'Dental Health Month: Schedule your child\'s dental check-up. Free screening available {date} at {time}. Healthy teeth = Healthy learning!'
                },
                {
                    'name': 'Nutrition Program',
                    'content': 'School Nutrition Program: {meal_type} served today features {healthy_ingredients}. Teaching children about balanced nutrition for better health.'
                },
                {
                    'name': 'Mental Health Support',
                    'content': 'Mental Health Awareness: School counselors available for students. If your child seems stressed or anxious, please contact us. Support is confidential.'
                },
                {
                    'name': 'Physical Education',
                    'content': 'PE Day Tomorrow! Don\'t forget sports uniform and water bottle. Physical activity is essential for healthy development. Exciting games planned!'
                },
                {
                    'name': 'Health Screening',
                    'content': 'Health Screening: {screening_type} for all students {grade_level} will be conducted {date}. No preparation needed. Results shared with parents.'
                },
            ],
            'General Communications': [
                {
                    'name': 'Welcome Message',
                    'content': 'Welcome to {school_name}! We are excited to have {student_name} join our school community. Please contact us if you need any assistance.'
                },
                {
                    'name': 'Contact Update',
                    'content': 'Please update your contact information. Current emergency contact: {current_contact}. Visit the school office or call {office_number}.'
                },
                {
                    'name': 'Newsletter Reminder',
                    'content': 'School Newsletter now available! Read about upcoming events, student achievements, and important announcements. Check your email or school website.'
                },
                {
                    'name': 'Transportation Change',
                    'content': 'Transportation Update: {student_name} will now use {new_transport} route {route_number}. Pick-up time: {time}. Contact: {transport_coordinator}'
                },
                {
                    'name': 'Facility Maintenance',
                    'content': 'Facility Notice: {facility_area} will be closed for maintenance from {start_date} to {end_date}. Alternative arrangements: {alternative}.'
                },
                {
                    'name': 'Staff Change',
                    'content': 'Staff Update: Welcome {new_staff_name} as our new {position}! {previous_staff} has {reason_for_leaving}. Contact: {contact_info}'
                },
            ]
        }

        total_created = 0

        for organization in organizations:
            self.stdout.write(f'Seeding templates for organization: {organization.name}')

            for category, templates in template_categories.items():
                for template_data in templates:
                    # Check if template already exists
                    existing = OrgSMSTemplate.objects.filter(
                        organization=organization,
                        name=template_data['name']
                    ).exists()

                    if not existing:
                        OrgSMSTemplate.objects.create(
                            organization=organization,
                            name=f"{category}: {template_data['name']}",
                            content=template_data['content'],
                            is_pre_built=True
                        )
                        total_created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'  Created: {template_data["name"]}')
                        )
                    else:
                        self.stdout.write(
                            f'  Skipped (exists): {template_data["name"]}'
                        )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {total_created} SMS templates across {len(organizations)} organizations')
        )

        # Summary by category
        self.stdout.write('\nTemplate Summary:')
        for category, templates in template_categories.items():
            self.stdout.write(f'  {category}: {len(templates)} templates')