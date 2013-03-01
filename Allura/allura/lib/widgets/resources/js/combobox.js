(function($) {
  $.widget('ui.combobox', {

    options: {
      source_url: ''  // caller must provide this
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

      function removeIfInvalid(element) {
        var value = $(element).val(),
            matcher = new RegExp('^' + $.ui.autocomplete.escapeRegex(value) + '$'),
            valid = false;
        select.children('option').each(function() {
          if ($(this).text().match(matcher)) {
            this.selected = valid = true;
            return false;
          }
        });

        if (!valid) {
          $(element).val('');
          select.val('');
          input.data('autocomplete').term = '';
        }
      }

      input = $('<input>')
              .appendTo(wrapper)
              .val(value)
              .attr('title', '')
              .addClass('ui-state-default ui-combobox-input')
              .autocomplete({
                delay: 0,
                minLength: 0,
                source: function (request, response) {
                  var matcher = new RegExp($.ui.autocomplete.escapeRegex(request.term), 'i');
                  response(select.children('option').map(function() {
                    var text = $(this).text();
                    if (this.value && (!request.term || matcher.test(text))) {
                      return {
                        label: text.replace(
                                 new RegExp(
                                   '(?![^&;]+;)(?!<[^<>]*)(' +
                                   $.ui.autocomplete.escapeRegex(request.term) +
                                   ')(?![^<>]*>)(?![^&;]+;)', 'gi'
                                 ), '<strong>$1</strong>'),
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
              }).addClass('ui-widget ui-widget-content ui-corner-left');

      input.data('autocomplete')._renderItem = function(ul, item) {
        return $('<li>')
          .data('item.autocomplete', item)
          .append('<a>' + item.label + '</a>')
          .appendTo(ul);
      };

      $('<a>')
        .attr('tabIndex', -1)
        .attr('title', 'Show all options')
        .appendTo(wrapper)
        .button({
          icons: {
            primary: 'ui-icon-triangle-1-s'
          },
          text: false
        })
        .removeClass('ui-corner-all')
        .addClass('ui-corner-right ui-combobox-toggle')
        .mousedown(function() {
          wasOpen = input.autocomplete('widget').is(':visible');
        })
        .click(function() {
          input.focus();
          if (wasOpen) {
            return;
          }
          input.autocomplete('search', '');
        });
    },

    _destroy: function() {
      this.wrapper.remove();
      this.element.show();
    }
  });
})(jQuery);
