function add_field(name, type, options){
    var $new_field = $('<div class="custom-field">'
                     +   '<label>Name: </label><input class="field-name" type="text"/><br/>'
                     +   '<label>Type: </label>'
                     +   '<select>'
                     +     '<option value="string">string</option>'
                     +     '<option value="number">number</option>'
                     +     '<option value="date">date</option>'
                     +     '<option value="select">select</option>'
                     +   '</select><br/>'
                     +   '<span class="options-wrapper"><label>Options: </label><input class="field-options" type="text"/><br/></span>'
                     +   '<button onclick="delete_field(this)">Delete</button>'
                     + '</div>');

    name && $new_field.find('input.field-name').val(name);
    type && $new_field.find('option:contains('+type+')').attr('selected', 'selected');
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
                        + '"name":"' + $this.find('input.field-name').val() + '",'
                        + '"type":"' + $this.find('select').val() + '",'
                        + '"options":"' + $this.find('input.field-options').val() + '"'
                        + '}'
                    );
                }).
                get().
                join(',') + ']';
    $.post('set_custom_fields', { custom_fields: json });
}

function show_hide_options(){
    var $this=$(this), show=$this.val()==='select';
    $this.closest('div.custom-field').find('span.options-wrapper').toggle(show)
}

$(function(){
    $('div.custom-field-stub').each(function(){
        var $this=$(this), name=$this.attr('data-name'), type=$this.attr('data-type'), options=$this.attr('data-options');
        add_field(name, type, options);
        $this.remove();
    });
    $('#custom-field-list').sortable();
});
