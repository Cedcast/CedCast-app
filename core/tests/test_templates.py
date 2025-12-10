from django.template.loader import get_template
from django.test import SimpleTestCase
import os


class TemplateCompileTest(SimpleTestCase):
    def test_all_templates_compile(self):
        tdir = os.path.join('core', 'templates')
        for root, dirs, files in os.walk(tdir):
            for f in files:
                if f.endswith('.html'):
                    # rel should be the path relative to core/templates
                    rel = os.path.relpath(os.path.join(root, f), tdir)
                    # Attempt to load/compile the template; get_template will raise on syntax errors
                    get_template(rel)
