function add_field(name, type){
    var $new_field = $('<div class="custom-field">'
                     +   '<label>Name:</label><input class="field-name" type="text"/><br/>'
                     +   '<label>Type:</label>'
                     +   '<select>'
                     +     '<option value="string">string</option>'
                     +     '<option value="number">number</option>'
                     +     '<option value="date">date</option>'
                     +   '</select><br/>'
                     +   '<button onclick="delete_field(this)">Delete</button>'
                     + '</div>');

    name && $new_field.find('input.field-name').val(name);
    type && $new_field.find('option:contains('+type+')').attr('selected', 'selected')

    $('#custom-field-list').append($new_field);
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
                        + '"type":"' + $this.find('select').val() + '"'
                        + '}'
                    );
                }).
                get().
                join(',') + ']';
    $.post('set_custom_fields', { custom_fields: json });
}

$(function(){
    $('div.custom-field-stub').each(function(){
        var $this=$(this), name=$this.attr('data-name'), type=$this.attr('data-type');
        add_field(name, type);
        $this.remove();
    });
    $('#custom-field-list').sortable();
});
