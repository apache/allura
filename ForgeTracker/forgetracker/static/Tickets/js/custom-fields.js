function add_field(label, type, options){
    var $new_field = $('<div class="custom-field">'
                     +   '<div class="span-3 clear"><label>Label: </label></div><div class="span-13 last"><input class="field-label title wide" type="text"/></div>'
                     +   '<div class="span-3 clear"><label>Type: </label></div>'
                     +   '<div class="span-13 last"><select class="title wide">'
                     +     '<option value="string">text</option>'
                     +     '<option value="sum">sum</option>'
                     +     '<option value="number">number</option>'
                     +     '<option value="boolean">boolean</option>'
                     +     '<option value="select">select</option>'
                     +   '</select></div>'
                     +   '<span class="options-wrapper"><div class="span-3 clear"><label>Options: </label></div>'
                     +   '<div class="span-13 last"><input class="field-options title wide" type="text"/></div></span>'
                     +   '<div class="push-3 span-13 last"><input type="button" onclick="delete_field(this)" value="Delete" class="ui-state-default ui-button ui-button-text"/></div>'
                     +   '<div class="clear clearfix"/>'
                     + '</div>');

    label && $new_field.find('input.field-label').val(label);
    type && $new_field.find('option[value="'+type+'"]').attr('selected', 'selected');
    options && $new_field.find('input.field-options').val(options);

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
        alert('Every custom field must have a label.')
    }
    else{
        var json = '[' + $('#custom-field-list>div.custom-field').
                    map(function(){
                        var $this=$(this);
                        return ('{'
                            + '"label":"' + $this.find('input.field-label').val() + '",'
                            + '"type":"' + $this.find('select').val() + '",'
                            + '"options":"' + $this.find('input.field-options').val() + '"'
                            + '}'
                        );
                    }).
                    get().
                    join(',') + ']';
        $.post('set_custom_fields', { custom_fields: json }, function(){
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
        var $this=$(this), label=$this.attr('data-label'), type=$this.attr('data-type'), options=$this.attr('data-options');
        add_field(label, type, options);
        $this.remove();
    });
    $('#custom-field-list').sortable();
    manage_messages();
});
