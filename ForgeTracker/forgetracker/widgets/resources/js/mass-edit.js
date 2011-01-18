function update_tickets(){
    var $checked=$('tbody.ticket-list input:checked'), count=$checked.length;

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
        flash('Updated '+count+' ticket'+(count!=1 ? 's' : ''))
        location.reload();
    });
}

$(function(){
    $('#assigned_to').val('');
    $('#select_all').click(function(){
        if(this.checked){
            $('tbody.ticket-list input[type=checkbox]').attr('checked', 'checked');
        }
        else{
            $('tbody.ticket-list input[type=checkbox]').removeAttr('checked');
        }
    });
});
