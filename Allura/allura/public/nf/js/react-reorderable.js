(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.ReactReorderable = f()}})(function(){var define,module,exports;return (function e(t,n,r){function s(o,u){if(!n[o]){if(!t[o]){var a=typeof require=="function"&&require;if(!u&&a)return a(o,!0);if(i)return i(o,!0);var f=new Error("Cannot find module '"+o+"'");throw f.code="MODULE_NOT_FOUND",f}var l=n[o]={exports:{}};t[o][0].call(l.exports,function(e){var n=t[o][1][e];return s(n?n:e)},l,l.exports,e,t,n,r)}return n[o].exports}var i=typeof require=="function"&&require;for(var o=0;o<r.length;o++)s(r[o]);return s})({1:[function(require,module,exports){
(function (global){
'use strict';

var React = (typeof window !== "undefined" ? window['React'] : typeof global !== "undefined" ? global['React'] : null);
var findDOMNode = (typeof window !== "undefined" ? window['ReactDOM'] : typeof global !== "undefined" ? global['ReactDOM'] : null).findDOMNode;
var ReactDrag = (typeof window !== "undefined" ? window['ReactDrag'] : typeof global !== "undefined" ? global['ReactDrag'] : null);

function getClosestReorderable(el) {
  while (el) {
    if (el.className &&
        el.className.indexOf('react-reorderable-item') >= 0) {
      return el;
    }
    el = el.parentNode;
  }
  return null;
}

var SIBLING_TYPES = {
  NONE: 0,
  NEXT: 1,
  PREVIOUS: 2
};

function getControlPosition(e) {
  var position = (e.touches && e.touches[0]) || e;
  return {
    clientX: position.clientX,
    clientY: position.clientY
  };
}

function getHorizontalSiblingType(e, node) {
  var rect = node.getBoundingClientRect();
  var nodeTop = rect.top;
  var nodeLeft = rect.left;
  var width = rect.width;
  var height = rect.height;
  var position = getControlPosition(e);

  if (position.clientY < nodeTop || position.clientY > nodeTop + height) {
    return SIBLING_TYPES.NONE;
  }
  if (position.clientX > nodeLeft && position.clientX < nodeLeft + 1 / 2 * width) {
    return SIBLING_TYPES.NEXT;
  }
  if (position.clientX > nodeLeft + 1 / 2 * width && position.clientX < nodeLeft + width) {
    return SIBLING_TYPES.PREVIOUS;
  }
  return SIBLING_TYPES.NONE;
}

function getVerticalSiblingType(e, node) {
  var rect = node.getBoundingClientRect();
  var nodeTop = rect.top;
  var nodeLeft = rect.left;
  var width = rect.width;
  var height = rect.height;
  var position = getControlPosition(e);

  if (position.clientX < nodeLeft || position.clientX > nodeLeft + width) {
    return SIBLING_TYPES.NONE;
  }
  if (position.clientY > nodeTop && position.clientY < nodeTop + 1 / 2 * height) {
    return SIBLING_TYPES.NEXT;
  }
  if (position.clientY > nodeTop + 1 / 2 * height && position.clientY < nodeTop + height) {
    return SIBLING_TYPES.PREVIOUS;
  }
  return SIBLING_TYPES.NONE;
}

function getSiblingNode(e, node, mode) {
  var p = node.parentNode;
  var siblings = p.children;
  var current;
  var done = false;
  var result = {};
  mode = mode || 'list';
  for (var i = 0; i < siblings.length && !done; i += 1) {
    current = siblings[i];
    if (current.getAttribute('data-reorderable-key') !==
        node.getAttribute('data-reorderable-key')) {
      // The cursor should be around the middle of the item
      var siblingType;
      if (mode === 'list') {
        siblingType = getVerticalSiblingType(e, current);
      } else {
        siblingType = getHorizontalSiblingType(e, current);
      }
      if (siblingType !== SIBLING_TYPES.NONE) {
        result.node = current;
        result.type = siblingType;
        return result;
      }
    }
  }
  return result;
}

function indexChildren(children) {
  var prefix = 'node-';
  var map = {};
  var ids = [];
  var id;
  for (var i = 0; i < children.length; i += 1) {
    var id = prefix + (i + 1);
    ids.push(id);
    children[i] = React.createElement('div', {
      className: 'react-reorderable-item',
      key: id,
      'data-reorderable-key': id
    }, children[i]);
    map[id] = children[i];
  }
  return { map: map, ids: ids };
}

function is(elem, selector) {
  var matches = elem.parentNode.querySelectorAll(selector);
  for (var i = 0; i < matches.length; i += 1) {
    if (elem === matches[i]) {
      return true;
    }
  }
  return false;
}

function getNodesOrder(current, sibling, order) {
  var currentKey = current.getAttribute('data-reorderable-key');
  var currentPos = order.indexOf(currentKey);
  order.splice(currentPos, 1);
  var siblingKey = sibling.node.getAttribute('data-reorderable-key');
  var siblingKeyPos = order.indexOf(siblingKey);
  if (sibling.type === SIBLING_TYPES.PREVIOUS) {
    order.splice(siblingKeyPos + 1, 0, currentKey);
  } else {
    order.splice(siblingKeyPos, 0, currentKey);
  }
  return order;
}


var ReactReorderable = React.createClass({
  componentWillMount: function () {
    window.addEventListener('mouseup', this._mouseupHandler = function () {
      this.setState({
        mouseDownPosition: null
      });
    }.bind(this));
  },
  componentWillUnmount: function () {
    window.removeEventListener('mouseup', this._mouseupHandler);
  },
  componentWillReceiveProps: function (nextProps) {
    if (nextProps.children) {
      var res = indexChildren(nextProps.children);
      this.setState({
        order: res.ids,
        reorderableMap: res.map
      });
    }
  },
  getInitialState: function () {
    var res = indexChildren(this.props.children);
    return {
      order: res.ids,
      startPosition: null,
      activeItem: null,
      reorderableMap: res.map
    };
  },
  onDragStop: function (e) {
    this.setState({
      activeItem: null,
      startPosition: null
    });
    this.props.onDrop(this.state.order.map(function (id) {
      return this.state.reorderableMap[id].props.children;
    }, this));
  },
  onDrag: function (e) {
    var handle = findDOMNode(this.refs.handle);
    var sibling = getSiblingNode(e, handle, this.props.mode);

    if (sibling && sibling.node) {
      var oldOrder = this.state.order.slice();
      var order = getNodesOrder(getClosestReorderable(handle), sibling, this.state.order);
      var changed = false;
      for (var i = 0; i < order.length && !changed; i += 1) {
        if (order[i] !== oldOrder[i]) {
          changed = true;
        }
      }
      if (changed) {
        this.props.onChange(this.state.order.map(function (id) {
          return this.state.reorderableMap[id].props.children;
        }, this));
      }
      this.setState({
        order: order
      });
    }
  },
  onMouseDown: function (e) {
    var position;

    if (!this.props.handle || is(e.target, this.props.handle)) {
      position = getControlPosition(e);

      this.setState({
        mouseDownPosition: {
          x: position.clientX,
          y: position.clientY
        }
      });
    }
  },
  onTouchStart: function(e) {
    e.preventDefault(); // prevent scrolling
    this.onMouseDown(e);
  },
  onMouseMove: function (e) {
    var position;

    if (!this.state.activeItem) {
      var initial = this.state.mouseDownPosition;
      // Still not clicked
      if (!initial) {
        return;
      }

      position = getControlPosition(e);

      if (Math.abs(position.clientX - initial.x) >= 5 ||
          Math.abs(position.clientY - initial.y) >= 5) {
        var node = getClosestReorderable(e.target);
        var nativeEvent = e.nativeEvent;
        var id = node.getAttribute('data-reorderable-key');
        // React resets the event's properties
        this.props.onDragStart(this.state.reorderableMap[id]);
        this.activeItem = node;
        var parentNode = node.parentNode && node.parentNode.parentNode;
        this.setState({
          mouseDownPosition: null,
          activeItem: id,
          startPosition: {
            x: node.offsetLeft - (parentNode && parentNode.scrollLeft || 0),
            y: node.offsetTop - (parentNode && parentNode.scrollTop || 0)
          }
        }, function () {
          this.refs.handle.handleDragStart(nativeEvent);
        }.bind(this));
      }
    }
  },
  render: function () {
    var children = this.state.order.map(function (id) {
      var className = (this.state.activeItem) ? 'noselect ' : '';
      if (this.state.activeItem === id) {
        className += 'react-reorderable-item-active';
      }
      var oldClass = this.state.reorderableMap[id].props.className || '';
      if (oldClass) {
        className = oldClass + ' ' + className;
      }
      return React.cloneElement(
        this.state.reorderableMap[id], {
          key: 'reaorderable-' + id,
          ref: 'active',
          onMouseDown: this.onMouseDown,
          onMouseMove: this.onMouseMove,
          onTouchStart: this.onTouchStart,
          onTouchMove: this.onMouseMove,
          className: className
      });
    }, this);
    var handle;
    if (this.state.activeItem) {
      var pos = this.state.startPosition;
      var className = 'react-reorderable-handle';
      var oldClass = this.state.reorderableMap[this.state.activeItem].props.className || '';
      if (oldClass) {
        className = oldClass + ' ' + className;
      }
      handle = React.cloneElement(
        this.state.reorderableMap[this.state.activeItem], {
          className: className
      });
      handle =
        React.createElement(ReactDrag, {
          onStop: this.onDragStop,
          onDrag: this.onDrag,
          ref: 'handle',
          start: { x: pos.x, y: pos.y }
        }, handle);
    }
    return React.createElement('div', {
        ref: 'wrapper'
      }, children, handle);
  }
});

ReactReorderable.propTypes = {
  onDragStart: React.PropTypes.func,
  onDrag: React.PropTypes.func,
  onDrop: React.PropTypes.func,
  onChange: React.PropTypes.func
};

ReactReorderable.defaultProps = {
  onDragStart: function () {},
  onDrag: function () {},
  onDrop: function () {},
  onChange: function () {}
};

module.exports = ReactReorderable;


}).call(this,typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
},{}]},{},[1])(1)
});