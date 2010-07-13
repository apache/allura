function add_field(label, type, options, show_in_search){
    var $new_field = $('<div class="custom-field">'
                     +   '<div class="span-3 clear"><label>Label: </label></div><div class="span-9 last"><input class="field-label" type="text"/></div>'
                     +   '<div class="span-3 clear"><label>Type: </label></div>'
                     +   '<div class="span-9 last"><select>'
                     +     '<option value="string">text</option>'
                  // +     '<option value="sum">sum</option>'
                     +     '<option value="number">number</option>'
                     +     '<option value="boolean">boolean</option>'
                     +     '<option value="select">select</option>'
                     +   '</select></div>'
                     +   '<span class="options-wrapper"><div class="span-3 clear"><label>Options: </label></div>'
                     +   '<div class="span-9 last"><input class="field-options" type="text"/></div></span>'
                     +   '<div class="span-3 clear"><label>Show in search: </label></div>'
                     +   '<div class="span-9 last">'
                     +   '  <input type="checkbox" class="field-show-in-search" />'
                     +   '</div>'
                     +   '<div class="span-3 clear"><label>&nbsp;</label></div>'
                     +   '<div class="span-9 last"><input type="button" onclick="delete_field(this)" value="Delete"/></div>'
                     +   '<div class="clear clearfix"/>'
                     + '</div>');

    label && $new_field.find('input.field-label').val(label);
    type && $new_field.find('option[value="'+type+'"]').attr('selected', 'selected');
    options && $new_field.find('input.field-options').val(options);
    show_in_search && $new_field.find('input.field-show-in-search').attr('checked', show_in_search);

    $('#custom-field-list').append($new_field);

    $new_field.find('select').change(show_hide_options).change();
    manage_messages();
}

function delete_field(el){
    $(el).closest('div.custom-field').remove();
    manage_messages();
}

function save_fields(){
    var foundBlank = false;
    $('#custom-field-list>div.custom-field input.field-label').each(function(ele){
        if(this.value==''){
            foundBlank = true;
        }
    });
    if(foundBlank){
        flash('Every custom field must have a label.', 'error')
    }
    else{
        var json = '[' + $('#custom-field-list>div.custom-field').
                    map(function(){
                        var $this=$(this);
                        return ('{'
                            + '"label":"' + $this.find('input.field-label').val() + '",'
                            + '"type":"' + $this.find('select').val() + '",'
                            + '"show_in_search":' + $this.find('input.field-show-in-search').is(':checked') + ','
                            + '"options":"' + $this.find('input.field-options').val() + '"'
                            + '}'
                        );
                    }).
                    get().
                    join(',') + ']';
        $.post('set_custom_fields', {
            custom_fields: json,
            status_names: $('#status_names').val(),
            milestone_names: $('#milestone_names').val()
        }, function(){
            location.reload();
        });
    }
}

function show_hide_options(){
    var $this=$(this), show=$this.val()==='select';
    $this.closest('div.custom-field').find('span.options-wrapper').toggle(show)
}

function manage_messages(){
    if($('div.custom-field').length){
        $('#no_fields_message').hide();
        $('#has_fields_message').show();
    }
    else{
        $('#no_fields_message').show();
        $('#has_fields_message').hide();
    }
}

$(function(){
    $('div.custom-field-stub').each(function(){
        var $this = $(this);
        var label = $this.attr('data-label');
        var type = $this.attr('data-type');
        var options = $this.attr('data-options');
        var show_in_search = $this.attr('data-show-in-search') == 'true';

        add_field(label, type, options, show_in_search);
        $this.remove();
    });
    $('#custom-field-list').sortable();
    manage_messages();
});
