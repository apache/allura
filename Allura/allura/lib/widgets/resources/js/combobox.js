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

(function($) {
  $.widget('ui.combobox', {

    options: {
      source_url: null  // caller must provide this
    },

    _create: function() {
      var input,
          that = this,
          wasOpen = false,
          loaded = false,  // options list loaded with ajax already?
          select = this.element.hide(),
          selected = select.children(':selected'),
          value = selected.val() ? selected.text() : "",
          wrapper = this.wrapper = $('<span>')
            .addClass('ui-combobox')
            .insertAfter(select);

      function populateSelect(data) {
        select.children('option').remove();
        $('<option></option>').val('').appendTo(select);
        var selected_option_present = false;
        for (var i = 0; i < data.options.length; i++) {
          var label = data.options[i].label,
              value = data.options[i].value;         
          var option = $('<option>').text(label).val(value);
          if (selected.val() === value) {
            option.attr('selected', 'selected');  // select initial value, if any
            selected_option_present = true;
          }
          option.appendTo(select);
        }
        if (!selected_option_present) {
          selected.attr('selected', 'selected');
          selected.appendTo(select);
        }
        loaded = true;
        if (wasOpen) {
          input.autocomplete('search', input.val());  // trigger search to re-render options
        }
      }

      // Load options list with ajax and populate underlying select with loaded data
      $.get(this.options.source_url, populateSelect);

      function removeIfInvalid(element) {
        var value = $(element).val(),
            matcher = new RegExp('^' + $.ui.autocomplete.escapeRegex(value) + '$'),
            valid = false;
        select.children('option').each(function() {
          if ($(this).val().match(matcher)) {
            this.selected = valid = true;
            input.val(this.text);
            return false;
          }
        });

        if (!valid) {
          $(element).val('');
          select.val('');
          input.data('autocomplete').term = '';
          wrapper.children('.error').fadeIn('fast');
          setTimeout(function() {
            wrapper.children('.error').fadeOut('fast');
          }, 2500);
        }
      }

      input = $('<input>')
              .appendTo(wrapper)
              .val(value)
              .attr('title', '')
              .addClass('ui-combobox-input')
              .autocomplete({
                delay: 0,
                minLength: 0,
                source: function (request, response) {
                  if (!loaded) {
                    response([{
                      label: 'Loading...',
                      value: '',
                      option: {item: ''}
                    }]);
                    return;
                  }
                  var matcher = new RegExp($.ui.autocomplete.escapeRegex(request.term), 'i');
                  response(select.children('option').map(function() {
                    var text = $(this).text();
                    if (this.value && (!request.term || matcher.test(text))) {
                      var label = escape_html(text);
                      if (request.term) {
                        // highlight the matching chars with <strong>
                        label = label.replace(
                            new RegExp('(?![^&;]+;)(?!<[^<>]*)(' +
                                $.ui.autocomplete.escapeRegex(request.term) +
                                ')(?![^<>]*>)(?![^&;]+;)', 'gi'
                            ),
                            '<strong>$1</strong>'
                        );
                      }
                      return {
                        label: label,
                        value: text,
                        option: this
                      };
                    }
                  }));
                },
                select: function(event, ui) {
                  ui.item.option.selected = true;
                  that._trigger('selected', event, {item: ui.item.option});
                },
                change: function(event, ui) {
                  if (!ui.item) {
                    removeIfInvalid(this);
                  }
                }
              });

      input.autocomplete('instance')._renderItem = function(ul, item) {
        return $('<li>')
          .data('item.autocomplete', item)
          .append('<a>' + item.label + '</a>')
          .appendTo(ul);
      };

      function openDropdown() {
        wasOpen = input.autocomplete('widget').is(':visible');
        input.focus();
        if (wasOpen) {
          return;
        }
        input.autocomplete('search', '');
      }

      input.click(openDropdown);

      $('<span>')
        .text('▼')
        .attr('tabIndex', -1)
        .attr('title', 'Show all options')
        .appendTo(wrapper)
        .addClass('ui-combobox-toggle')
        .click(openDropdown);

      $('<div>')
        .hide()
        .addClass('error')
        .text('Choose a valid option')
        .appendTo(wrapper);
    },

    _destroy: function() {
      this.wrapper.remove();
      this.element.show();
    }
  });
})(jQuery);
