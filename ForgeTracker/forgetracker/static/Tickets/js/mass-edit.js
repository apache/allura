function update_tickets(){
    var $checked=$('input:checked'), count=$checked.length;

    if ( !count ) {
        $('#result').text('No tickets selected for update.');
        return;
    }

    var data={};
    data.selected = $checked.map(function(){ return this.name; }).get().join(',');
    $('#update-values').find('input, select').each(function(){
        this.value && (data[this.name]=this.value);
    });

    $.post('../update_tickets', data, function(){
        $('#result').text('Updated '+count+' ticket'+(count!=1 ? 's' : ''));
    });
}

$(function(){
    var $at=$('select[name=assigned_to]');
    // set the 'nobody' option to a value recognized by ../update_tickets
    $at.find('option[value=]').attr('value', '-');
    // but the default is 'no change'
    $at.prepend('<option selected="selected" value=""></option>');
});
