EasyWidgets Tutorial
=======================================

Intro
--------

EasyWidgets is a minimalistic reimplementation of TurboGears widgets.  A widget
provides one or more of the following features, all bundled together:

 * HTML markup (via a templating engine)
 * Validation (for forms)
 * Static resources to be injected into the rendered HTML page

This tutorial will demonstrate how to integrate widgets into a simple TurboGears
application as well as how to create your own widgets.

Prerequisites
-------------------

EasyWidgets is designed to work with Python 2.5 and 2.6 and with TurboGears 2.0
and 2.1.  It may work with other configurations, but most likely won't.  You
should be familiar with TurboGears2 concepts before starting this tutorial.  You
should have installed TurboGears2 and quickstarted a project before starting this
tutorial, as well as having installed EasyWidgets.  To install EasyWidgets, you
can use pip or easy_install::

    easy_install EasyWidgets

Integration
---------------

There are three integration points for widgets, each having to do with injecting
static resources in the rendered HTML.  The first of these is the static resource
controller.  This should be mounted on your root controller at the URL path
/_ew_resources/ as follows::

    import ew

    class Root(TGController):
        _ew_resources = ew.ResourceManager.get()

The second integration point is in your master.html template.  A minimalistic
master.html (in Genshi) is included below::

    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                          "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:py="http://genshi.edgewall.org/"
          xmlns:xi="http://www.w3.org/2001/XInclude"
          py:strip="True">
      <?python
         from ew import ResourceManager
         resource_manager = ResourceManager.get()
         resource_manager.register_widgets(c)
         ?>
      <head py:match="head" py:attrs="select('@*')">
        <meta content="text/html; charset=UTF-8" http-equiv="content-type" py:replace="''"/>
        <title py:replace="''">Your title goes here</title>
        <meta py:replace="select('*')"/>
        <py:for each="blob in resource_manager.emit('head_css')">$blob</py:for>
        <py:for each="blob in resource_manager.emit('head_js')">$blob</py:for>
      </head>
      <body py:match="body" py:attrs="select('@*')">
        <py:for each="blob in resource_manager.emit('body_top_js')">$blob</py:for>
        <div py:replace="select('*|text()')"/>
        <py:for each="blob in resource_manager.emit('body_js')">$blob</py:for>
      </body>
    </html>

Things to note in the minimalistic template above are the following:

`<?python` block
    This block imports the ResourceManager from EasyWIdgets and prepares to
    render static resources by inspecting the Pylons context object `c` and
    regsitering any widgets found there.

`head_css` block
    This `py:for` loop emits any resource definitions defined with the `head_css`
    location.  This will generally be CSS `<link>` and `<style>` blocks.

`head_js` block
    This `py:for` loop emits any resource definitions defined with the `head_js`
    location.  This should only be used for `<script>` blocks that should be
    included in the `<head>` section.

`body_top_js` block
    This `py:for` loop emits any resource definitions defined with the `body_top_js`
    location.  This should only be used for `<script>` blocks that should be
    included at the beginning of the `<body>` section.

`body_js` block
    This `py:for` loop emits any resource definitions defined with the `body_js`
    location.  This should only be used for `<script>` blocks that should be
    included at the end of the `<body>` section.  If in doubt as to where to
    include your `<script>`, it's best to use `body_js`, as this tends to speed
    up page rendering.

The final integration point is where we let EasyWidgets know what resources
should be made available.  This is achieved at application start-up time, most
conveniently in your `config/middleware.py`::

.. code-block:: python

    from ew import ResourceManager
    ...
    app = make_base_app(global_conf, full_stack=True, **app_conf)
    ResourceManager.register_all_resources()
    return app
    ...

Creating a Form
---------------------

Now that everything's set up and your master.html as been modified to take
advantage of EasyWidgets, it's time to create our first form.  Open up your
`controllers/root.py` and replace its contents with the following::

    from pylons import c
    from tg import expose
    import ew

    from ..lib.base import BaseController

    __all__ = ['RootController']

    class RootController(BaseController):
        _ew_resources = ew.ResourceManager.get()
        simple_form = ew.SimpleForm(
            fields=[
                ew.TextField(name='a'),
                ew.TextField(name='b'),
                ],
            submit_text='Save this form')

        @expose('ewtutorial.templates.index')
        def index(self, **kw):
            c.form = self.simple_form
            return dict()

Here we have defined a simple form with two inputs, a and b.  In order to see it
in action, we'll need to modify the `templates/index.html` file::

    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                          "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:py="http://genshi.edgewall.org/"
          xmlns:xi="http://www.w3.org/2001/XInclude">

      <xi:include href="master.html" />

    <head>
      <meta content="text/html; charset=UTF-8" http-equiv="content-type" py:replace="''"/>
      <title>Welcome to EasyWidgets</title>
    </head>

    <body>
      ${c.form.display()}
    </body>
    </html>

Now, if you restart your server and view http://localhost:8080, you should see
the new widget we just defined.  Nothing too special here.  But we're just
getting started.

Let's say we want to make a simple form with a single string input with a minimum
length of 8 characters (perhaps for a username).  Modify the form definition to
read::

   simple_form = ew.SimpleForm(
        fields=[
            ew.TextField(
                name='username',
                validator=UnicodeString(min=8, if_missing=None)),
            ],
        submit_text='Save this form')

Now, in order to enforce the validation, we will need to decorate the controller
with an `@validate` decorator, as well as do a couple more imports:

.. code-block:: python

    from formencode.validators import UnicodeString
    from tg import validate

    ...

    class RootController(...):
        ...
        @expose('ewtutorial.templates.index')
        @validate(simple_form)
        def index(self, **kw):
            ....

If you now restart your server and refresh the page, you will see the username
field displayed.  Try submitting the form with a short username, and notice how
the validator will reject anything shorter than 8 characters with an error message.

This form's kind of ugly, though, so let's enhance it by pulling in Dojo
(EasyWidgets includes a version of Dojo).  Modify the form definition to read::

   simple_form = ew.dojo.SimpleForm(
        fields=[
            ew.dojo.TextField(
                name='username',
                validator=UnicodeString(min=8, if_missing=None)),
            ],
        submit_text='Save this form')

and add the following import::

    import ew.dojo

Next, to get the correct theme, you'll need to modify your index.html to set a
class on the `<body>` tag::

    <body class="soria">

Now if you refresh, you should see a much nicer-styled form, complete with an
error message (if you enter a value that is too short, of course).

Now, let's update the form to be a bit nicer::

   simple_form = ew.dojo.SimpleForm(
        fields=[
            ew.dojo.TextField(
                name='username',
                label='Choose a user name',
                validator=UnicodeString(min=8, if_missing=None)),
            ew.dojo.DateField(
                name='birthdate',
                label='Date of Birth')
            ],
        submit_text='Save this form')

Now if you refresh the form you'll be greeted by a date field with a nice
calendar popup.  All without any additional CSS or HTML!

Now we have just been submitting the form back to the `index()` method up until
now.  It might be nicer to set things up a bit differently.  Update your controller
as follows::

    @expose('ewtutorial.templates.index')
    def index(self, **kw):
        c.form = self.simple_form
        return dict(action='action')

    @expose('ewtutorial.templates.action')
    @validate(simple_form, error_handler=index)
    def action(self, **kw):
        return dict(value=kw)

Now we will update our index.html::

    ...
    <body class="soria">
      ${c.form.display(action=action)}
    </body>
    ...

Now, we'll need a simple template `action.html` that displays the submitted data::

    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
              "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:py="http://genshi.edgewall.org/"
          xmlns:xi="http://www.w3.org/2001/XInclude">

      <xi:include href="master.html" />

      <head>
        <meta content="text/html; charset=UTF-8" http-equiv="content-type" py:replace="''"/>
        <title>Welcome to EasyWidgets</title>
      </head>

      <body class="soria">
        <a href="/">Go back</a>
        <pre>${repr(value)}</pre>
      </body>
    </html>

If we refresh, nothing seems to have changed.  But if we submit the form, we
should see the results::

    {'username': u'some_username', 'birthdate': datetime.date(2010, 2, 9)}

As you can see, the username has been validated and the date has been converted
to a Python `datetime` object.

Declaratively Extending Forms
-------------------------------------------

All this is nice, but the syntax has been a little clumsy.  Let's update our form
definition a bit:

.. code-block:: python

    class MyForm(ew.dojo.SimpleForm):
        class fields(ew.WidgetsList):
            username=ew.dojo.TextField(
                label='Choose a User Name',
                validator=UnicodeString(min=8)),
            birthdate=ew.dojo.DateField(
                label='Date of Birth')
        submit_text='Save This Form'

    class RootController(BaseController):
        _ew_resources=ew.ResourceManager.get()
        simple_form = MyForm()
    ...

Nice and declarative.  Not in particular how the `name` property for the fields
is picked up from their label in the `ew.FieldList`.

Complex Forms
----------------------

We can make arbitrarily complex forms by using `ew.FieldSet` and
`ew.RepeatingField`.  Try out the following complex form definition:

.. code-block:: python

    class MyComplexForm(ew.dojo.SimpleForm):
        class fields(ew.WidgetsList):
            user_info=ew.FieldSet(
                fields=[
                    ew.dojo.TextField(name='name'),
                    ew.dojo.TextField(name='address'),
                    ew.dojo.DateField(name='dob')])
            children=ew.RepeatedField(
                fields=[
                    ew.dojo.TextField(name='name')],
                repetitions=10)

        ...
        simple_form=MyComplexForm()
        ...
        @ew.variable_decode
        @expose('ewtutorial.templates.action')
        @validate(simple_form, error_handler=index)
        def action(self, **kw):
        ...

Notice how the user_info is collected into a `<fieldset>` and the children fields
are repeated down the page.  Notice how when you submit the form, the data is
'packed' according to the form layout.  This packing is performed by the
`@ew.variable_decode` decorator.

Notice how we specified 10 repetitions of the `children` field above.  If we
supply a value to the form, that value overrides the repetitions.  Let's add
another controller method:

.. code-block:: python

    from datetime import date
    ...
    class RootController(BaseController):
        ...
        @expose('ewtutorial.templates.display_value')
        def show_value(self):
            c.form = self.simple_form
            return dict(
                action='action',
                value=dict(
                    user_info=dict(
                        dob=date(1972,1,1),
                        name='Rick Copeland',
                        address='777 Main Street'),
                    children=[
                        dict(name='Matthew')]))

Now if we visit http://localhost:8080/show_value , we can see the filled-out
data.

Building Your Own Widgets
-----------------------------------

Up until now, we have shown how you can combine existing widgets in interesting
ways.  The real power of EasyWidgets is when you start building your own
widgets.  You'll generally want to subclass one of the widgets in EasyWidgets in
order to build your own form-style widget.  Some class attributes to be aware of
include:

template
    This class attribute specifies the dotted template name (just like the
    `@expose` decorator) used to render the widget.
params
    This class attribute is a list of strings which specifies which widget
    attributes should be included in the template context when rendering the widgeat.
perform_validation
    If this attribute is set to False, the widget will not participate in
    validation.  This is usually important only when creating widgets that need
    to be displayed as part of a form but have no input capabilities.
def resources():
    This method should return a list or iterator of resources (defined in
    `ew.resource`) that should be included on pages that require this widget.

Static Resources
----------------------

We mentioned the _ew_resources url earlier in the tutorial, but it wasn't
really clear how you'd get files into that directory.  EasyWidgets allows your
package to "register" a directory to be served by the ResourcesController via the
`[easy_widgets.resources]` entry point.  For instance, to register a URL path
'foo', you would use the following entry point:

    [easy_widgets.resources]
    some_string_currently_ignored=my.package.path:my_registration_function

`my_registration_function` would be some function that
calls the EasyWidgets registration function::

    def my_registration_function(manager):
        manager.register_directory(
            'foo', pkg_resources.resource_filename(
                'my.package.path', 'public/js/foo'))

Now everything in the `public/js/foo` directory will be served by the
ResourceController under the `_ew_resources/foo` directory.

ControllerWidget
-----------------------

By far the easiest way to make a custom widget is to instantiate a
ControllerWidget::

    @expose('ewtutorial.templates.custom_widget')
    @validate(dict(a=UnicodeString(min=4)))
    def custom_widget(**kw):
        return dict(kw, action='action')

    simple_form = ew.ControllerWidget(custom_widget)

Now if we visit the index page, we see our custom widget displayed in all its
glory.  The validator from the @validate decorator is used if we use the
`simple_form` to validate user input, and the template specified with the
`@expose` decorator is used to render the widget.  The actual controller method
is used to generate the context for the template just like a regular TurboGears controller.

Widget Hierarchies
-----------------------------

One of the primary design goals of EasyWidgets is making it simple to create
reusable components for inclusion in your TurboGears controllers.  In the
examples above, we've been focusing on creating forms using EasyWidgets, but you
can do much more with them.  For instance, consider a commenting system that
allows you to create, moderate, and edit posts.  In order to display an
individual post with all its functionality, we'd like to create a reusable "Post"
component.  For this, we'll create a new Widget type, the hierarchical widget
`HierWidget`::

    class HierWidget(ew.Widget):
        widgets = {}

        def __call__(self, **kw):
            response = super(HierWidget, self).__call__(**kw)
            response['widgets'] = self.widgets
            return response

        def resources(self):
            for w in self.widgets.itervalues():
                for r in w.resources():
                    yield r

All this widget does is define a class attribute `widgets` which specifies a dict
of widgets which will be included as children of this one.  The only additional
functionality is a new `resources()` method that allows child widgets' resources
to "bubble up" through to their parent widget.  Now, we can define our `Post`
class and all its subforms::

    class FlagPost(ew.SimpleForm):
        submit_text='Flag post as inappropriate or spam'

    class ModeratePost(ew.SimpleForm):
        class buttons(ew.WidgetsList):
            delete=ew.SubmitButton(label='Delete Post')
            spam=ew.SubmitButton(label='Spam Post')
        submit_text=None

    class EditPost(ew.SimpleForm):
        class fields(ew.WidgetsList):
            subject=ew.TextField()
            text=ew.TextArea()

    class Post(HierWidget):
        template='genshi:widgets.templates.post'
        params=['value']
        value=None
        widgets=dict(
            flag_post=FlagPost(),
            moderate_post=ModeratePost(),
            edit_post=EditPost(submit_text='Edit Post'))

Now the template for the `Post` is where things start to get interesting::

    <div xmlns="http://www.w3.org/1999/xhtml"
         xmlns:py="http://genshi.edgewall.org/">
        <h3><strong>$value.subject</strong> by
          <a href="${value.author().url()}">${value.author().display_name}</a>
          ${h.ago(value.timestamp)}
        </h3>
        <div class="content">
          <div style="float:right">
              <h3>Post Controls</h3>
              <div class="content">
                ${widgets.flag_post.display(value=value, action='flag')}
                ${widgets.moderate_post.display(value=value, action='moderate')}
                <h4>Edit Post</h4>
                ${widgets.edit_post.display(
                    value=value, submit_text='Edit', action='.')}
                <h4>Reply to Post</h4>
                 ${widgets.edit_post.display(
                     submit_text='Post Reply',
                     action=value.url()+'reply',
                     value=dict(
                         text=value.reply_text(),
                         subject=value.reply_subject()),
                   )}
                </div>
              </div>
            </div>
          </div>
          $value.text
        </div>
      </div>
    </div>

The only thing really interesting here is that we are able to use the `edit_post`
form both to update the existing post as well as to reply to the post.  But now
that we have this widget, we can include it in a `Thread` widget that displays
multiple posts::

    class Thread(HierWidget):
        template='genshi:widgets.templates.thread'
        params=['value']
        value=None
        widgets=dict(
            thread_header=ThreadHeader(),
            post_thread=PostThread(),
            post=Post(),
            edit_post=EditPost(submit_text='New Post'))



