/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/

/*global SimpleMDE, _replaceSelection, Memorable */
$(window).load(function() {
    if(!window.markdown_init){
        window.markdown_init = true;
        $('div.markdown_edit').each(function(){
            var $container = $(this);
            var $textarea = $('textarea', $container);

            var $help_area = $('div.markdown_help', $container);
            var $help_contents = $('div.markdown_help_contents', $container);

            // Override action for a few buttons
            var toolbar = [
              "bold", "italic", "heading", "|", "code",
              "quote", "unordered-list", "ordered-list",
              {
                name: 'table',
                action: drawTable,
                className: 'fa fa-table',
                title: 'Insert Table'
              },
              "horizontal-rule", "|",
              "link", "image",
              "preview",
              //"side-by-side",
              "fullscreen",
              {
                name: 'guide',
                action: show_help,
                className: 'fa fa-question-circle',
                title: 'Formatting Help'
              }
            ];

            var editor = new SimpleMDE({
              element: $textarea[0],
              autoDownloadFontAwesome: false,
              autofocus: false,
              spellChecker: false, // https://forge-allura.apache.org/p/allura/tickets/7954/
              indentWithTabs: false,
              tabSize: 4,
              toolbar: toolbar,
              previewRender: previewRender,
              parsingConfig: {
                allowAtxHeaderWithoutSpace: true,
                strikethrough: false,
                taskLists: false,
                fencedCodeBlocks: true // override gfm's limited fencing regex
              },
              blockStyles: {
                code: '~~~'
              },
              shortcuts: {
                  "drawLink": null,  // default is cmd-k, used for search in Firefox, better to preserve that
                  "toggleUnorderedList": null, // default is cmd-l, used to activate location bar
              }
            });
            Memorable.add(editor);
            // https://github.com/codemirror/CodeMirror/issues/1576#issuecomment-19146595
            // can't use simplemde's shortcuts settings, since those only hook into bindings set up for each button
            editor.codemirror.options.extraKeys.Home = "goLineLeft";
            editor.codemirror.options.extraKeys.End = "goLineRight";

            // user mentions support
            editor.codemirror.on("keyup", function (cm, event) {
              if(event.key === "@" || (event.shiftKey && event.keyCode === 50 /* "2" key */)) {
                CodeMirror.showHint(cm, CodeMirror.hint.alluraUserMentions, {
                  completeSingle: false
                });
              }
            });

            editor.render();

            // shared at https://github.com/codemirror/CodeMirror/issues/2143#issuecomment-140100969
            function updateSectionHeaderStyles(cm, change) {
              var lines = cm.lineCount();
              for (var i = Math.max(0, change.from.line-1); i <= Math.min(change.to.line+1, lines-1); i++) {
                var line = cm.getLineHandle(i);
                cm.removeLineClass(line, 'text', 'cm-header');
                cm.removeLineClass(line, 'text', 'cm-header-1');
                cm.removeLineClass(line, 'text', 'cm-header-2');
                var lineTokens = cm.getLineTokens(i);
                var tok = lineTokens[0];
                if (!tok || !tok.type || tok.type.indexOf('header') === -1) {
                  // first token could be some spaces, try 2nd
                  tok = lineTokens[1];
                }
                if (tok && tok.type && tok.type.indexOf('header') !== -1
                  && tok.string !== '#') { // not ATX header style, which starts with #
                  var classes = tok.type.
                    split(' ').
                    filter(function(cls) { return cls.indexOf('header') === 0; }).
                    map(function (cls) { return 'cm-' + cls; }).
                    join(' ');
                  var prev_line = cm.getLineHandle(i-1);
                  cm.addLineClass(prev_line, 'text', classes);
                }
              }
            }
            editor.codemirror.on("change", updateSectionHeaderStyles);
            updateSectionHeaderStyles(editor.codemirror, {from: {line: 0}, to: {line: editor.codemirror.lineCount()}});

            function drawTable(editor) {
              var cm = editor.codemirror;
              cm.replaceSelection(
                'Header | Header | Header\n' +
                '---------- | ---------- | ------ \n' +
                'Cell      | Cell       | Cell \n' +
                'Cell      | Cell       | Cell ');
              cm.focus();
            }

            function show_help(editor) {
              $help_contents.html('Loading...');
              $.get($help_contents.attr('data-url'), function (data) {
                $help_contents.html(data);
                var display_section = function(evt) {
                  var $all_sections = $('.markdown_syntax_section', $help_contents);
                  var $this_section = $(location.hash.replace('#', '.'), $help_contents);
                  if ($this_section.length === 0) {
                    $this_section = $('.md_ex_toc', $help_contents);
                  }
                  $all_sections.addClass('hidden_in_modal');
                  $this_section.removeClass('hidden_in_modal');
                  $('.markdown_syntax_toc_crumb').toggle(!$this_section.is('.md_ex_toc'));
                };
                $('.markdown_syntax_toc a', $help_contents).click(display_section);
                $(window).bind('hashchange', display_section); // handle back button
              });
              $help_area.lightbox_me();
            }

            function previewRender(text, preview) {
              var cval = $.cookie('_session_id');
              $.post('/nf/markdown_to_html', {
                markdown: text,
                project: $('input.markdown_project', $container).val(),
                neighborhood: $('input.markdown_neighborhood', $container).val(),
                app: $('input.markdown_app', $container).val(),
                _session_id: cval
              },
              function(resp) {
                preview.innerHTML = resp;
              });
              return 'Loading...';
            }

            $('.close', $help_area).bind('click', function() {
              $help_area.hide();
            });
        });
    }
});
