function add_field(label, type, options){
    var $new_field = $('<div class="custom-field">'
                     +   '<div class="span-3"><label>Label: </label></div><div class="span-15 last"><input class="field-label" type="text"/></div>'
                     +   '<div class="span-3"><label>Type: </label></div>'
                     +   '<div class="span-15 last"><select>'
                     +     '<option value="string">text</option>'
                     +     '<option value="sum">number</option>'
                     +     '<option value="select">select</option>'
                     +   '</select></div>'
                     +   '<span class="options-wrapper"><div class="span-3"><label>Options: </label></div>'
                     +   '<div class="span-15 last"><input class="field-options" type="text"/></div></span>'
                     +   '<button onclick="delete_field(this)">Delete</button>'
                     + '</div>');

    label && $new_field.find('input.field-label').val(label);
    type && $new_field.find('option[value="'+type+'"]').attr('selected', 'selected');
    options && $new_field.find('input.field-options').val(options);

    $('#custom-field-list').append($new_field);

    $new_field.find('select').change(show_hide_options).change();
}

function delete_field(el){
    $(el).closest('div.custom-field').remove();
}

function save_fields(){
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

function show_hide_options(){
    var $this=$(this), show=$this.val()==='select';
    $this.closest('div.custom-field').find('span.options-wrapper').toggle(show)
}

$(function(){
    $('div.custom-field-stub').each(function(){
        var $this=$(this), label=$this.attr('data-label'), type=$this.attr('data-type'), options=$this.attr('data-options');
        add_field(label, type, options);
        $this.remove();
    });
    $('#custom-field-list').sortable();
});
