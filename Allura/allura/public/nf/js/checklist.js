/*jslint white: true, vars: true */
/*global Checklists, jQuery */

var Checklists = (function($) {

    "use strict";
    
    // makes Markdown checklists interactive
    // `container` is either a DOM element, jQuery collection or selector containing
    // the Markdown content
    // `retriever` is a function being passed the respective checkbox and a
    // callback - the latter is epxected to be called with the container's raw
    // Markdown source
    // `storer` is a function being passed the updated Markdown content, the
    // respective checkbox and a callback
    // both functions' are invoked with the respective `Checklists` instance as
    // execution context (i.e. `this`)
    function Checklists(container, retriever, storer) {
        this.container = container.jquery ? container : $(container);
        this.retriever = retriever;
        this.storer = storer;
    
        var checklists = $(".checklist", container);
        checklists.find(this.checkboxSelector).prop("disabled", false);
        var self = this;
        checklists.on("change", this.checkboxSelector, function() {
            var args = Array.prototype.slice.call(arguments);
            args.push(self);
            self.onChange.apply(this, args);
        });
    }
    Checklists.prototype.checkboxSelector = "> li > input:checkbox";
    Checklists.prototype.onChange = function(ev, self) {
        var checkbox = $(this).prop("disabled", true);
        var index = $("ul" + self.checkboxSelector, self.container).index(this);
        var reactivate = function() { checkbox.prop("disabled", false); };
        self.retriever(checkbox, function(markdown) {
            markdown = self.toggleCheckbox(index, markdown);
            self.storer(markdown, checkbox, reactivate);
        });
    };
    Checklists.prototype.toggleCheckbox = function(index, markdown) {
        var pattern = /^([*-]) \[([ Xx])\]/mg; // XXX: duplicates server-side logic!?
        var count = 0;
        return markdown.replace(pattern, function(match, prefix, marker) {
            if(count === index) {
                marker = marker === " " ? "x" : " ";
            }
            count++;
            return prefix + " [" + marker + "]";
        });
    };
    
    return Checklists;
    
    }(jQuery));