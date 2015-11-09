(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.ReactDrag = f()}})(function(){var define,module,exports;return (function e(t,n,r){function s(o,u){if(!n[o]){if(!t[o]){var a=typeof require=="function"&&require;if(!u&&a)return a(o,!0);if(i)return i(o,!0);var f=new Error("Cannot find module '"+o+"'");throw f.code="MODULE_NOT_FOUND",f}var l=n[o]={exports:{}};t[o][0].call(l.exports,function(e){var n=t[o][1][e];return s(n?n:e)},l,l.exports,e,t,n,r)}return n[o].exports}var i=typeof require=="function"&&require;for(var o=0;o<r.length;o++)s(r[o]);return s})({1:[function(require,module,exports){
(function (global){
'use strict';

var React = (typeof window !== "undefined" ? window['React'] : typeof global !== "undefined" ? global['React'] : null);
var findDOMNode = (typeof window !== "undefined" ? window['ReactDOM'] : typeof global !== "undefined" ? global['ReactDOM'] : null).findDOMNode;

function classNames() {
  var classes = '';
  for (var i = 0; i < arguments.length; i++) {
    var arg = arguments[i];
    if (!arg) continue;
    var argType = typeof arg;
    if ('string' === argType || 'number' === argType) {
      classes += ' ' + arg;
    } else if (Array.isArray(arg)) {
      classes += ' ' + classNames.apply(null, arg);
    } else if ('object' === argType) {
      for (var key in arg) {
        if (arg.hasOwnProperty(key) && arg[key]) {
          classes += ' ' + key;
        }
      }
    }
  }
  return classes.substr(1);
}

var emptyFunction = function () {};
var CX = classNames;

function createUIEvent(draggable) {
  return {
    position: {
      top: draggable.state.pageY,
      left: draggable.state.pageX
    }
  };
}

function canDragY(draggable) {
  return draggable.props.axis === 'both' ||
      draggable.props.axis === 'y';
}

function canDragX(draggable) {
  return draggable.props.axis === 'both' ||
      draggable.props.axis === 'x';
}

function isFunction(func) {
  return typeof func === 'function' ||
    Object.prototype.toString.call(func) === '[object Function]';
}

// @credits https://gist.github.com/rogozhnikoff/a43cfed27c41e4e68cdc
function findInArray(array, callback) {
  for (var i = 0, length = array.length, element = null; i < length; i += 1) {
    element = array[i];
    if (callback.apply(callback, [element, i, array])) {
      return element;
    }
  }
}

function matchesSelector(el, selector) {
  var method = findInArray([
    'matches',
    'webkitMatchesSelector',
    'mozMatchesSelector',
    'msMatchesSelector',
    'oMatchesSelector'
  ], function (method) {
    return isFunction(el[method]);
  });

  return el[method].call(el, selector);
}

// @credits:
// http://stackoverflow.com/questions/4817029/whats-the-best-way-to-detect-a-touch-screen-device-using-javascript/4819886#4819886
/* Conditional to fix node server side rendering of component */
if (typeof window === 'undefined') {
    // Do Node Stuff
  var isTouchDevice = false;
} else {
  // Do Browser Stuff
  var isTouchDevice = 'ontouchstart' in window // works on most browsers
    || 'onmsgesturechange' in window; // works on ie10 on ms surface
  // Check for IE11
  try {
    document.createEvent('TouchEvent');
  } catch (e) {
    isTouchDevice = false;
  }

}

// look ::handleDragStart
//function isMultiTouch(e) {
//  return e.touches && Array.isArray(e.touches) && e.touches.length > 1
//}

/**
 * simple abstraction for dragging events names
 * */
var dragEventFor = (function () {
  var eventsFor = {
    touch: {
      start: 'touchstart',
      move: 'touchmove',
      end: 'touchend'
    },
    mouse: {
      start: 'mousedown',
      move: 'mousemove',
      end: 'mouseup'
    }
  };
  return eventsFor[isTouchDevice ? 'touch' : 'mouse'];
})();

/**
 * get {pageX, pageY} positions of control
 * */
function getControlPosition(e) {
  var position = (e.touches && e.touches[0]) || e;
  return {
    pageX: position.pageX,
    pageY: position.pageY
  };
}

function getBoundPosition(pageX, pageY, bound, target) {
  if (bound) {
    if ((typeof bound !== 'string' && bound.toLowerCase() !== 'parent') &&
        (typeof bound !== 'object')) {
      console.warn('Bound should either "parent" or an object');
    }
    var par = target.parentNode;
    var topLimit = bound.top || 0;
    var leftLimit = bound.left || 0;
    var rightLimit = bound.right || par.offsetWidth;
    var bottomLimit = bound.bottom || par.offsetHeight;
    pageX = Math.min(pageX, rightLimit - target.offsetWidth);
    pageY = Math.min(pageY, bottomLimit - target.offsetHeight);
    pageX = Math.max(leftLimit, pageX);
    pageY = Math.max(topLimit, pageY);
  }
  return {
    pageX: pageX,
    pageY: pageY
  };
}

function addEvent(el, event, handler) {
  if (!el) { return; }
  if (el.attachEvent) {
    el.attachEvent('on' + event, handler);
  } else if (el.addEventListener) {
    el.addEventListener(event, handler, true);
  } else {
    el['on' + event] = handler;
  }
}

function removeEvent(el, event, handler) {
  if (!el) { return; }
  if (el.detachEvent) {
    el.detachEvent('on' + event, handler);
  } else if (el.removeEventListener) {
    el.removeEventListener(event, handler, true);
  } else {
    el['on' + event] = null;
  }
}

var ReactDrag = React.createClass({
  displayName: 'Draggable',

  propTypes: {
    /**
     * `axis` determines which axis the draggable can move.
     *
     * 'both' allows movement horizontally and vertically.
     * 'x' limits movement to horizontal axis.
     * 'y' limits movement to vertical axis.
     *
     * Defaults to 'both'.
     */
    axis: React.PropTypes.oneOf(['both', 'x', 'y']),

    /**
     * `handle` specifies a selector to be used as the handle
     * that initiates drag.
     *
     * Example:
     *
     * ```jsx
     *   var App = React.createClass({
     *       render: function () {
     *         return (
     *            <Draggable handle=".handle">
     *              <div>
     *                  <div className="handle">Click me to drag</div>
     *                  <div>This is some other content</div>
     *              </div>
     *           </Draggable>
     *         );
     *       }
     *   });
     * ```
     */
    handle: React.PropTypes.string,

    /**
     * `cancel` specifies a selector to be used to prevent drag initialization.
     *
     * Example:
     *
     * ```jsx
     *   var App = React.createClass({
     *       render: function () {
     *           return(
     *               <Draggable cancel=".cancel">
     *                   <div>
     *             <div className="cancel">You can't drag from here</div>
     *            <div>Dragging here works fine</div>
     *                   </div>
     *               </Draggable>
     *           );
     *       }
     *   });
     * ```
     */
    cancel: React.PropTypes.string,

    /**
     * `grid` specifies the x and y that dragging should snap to.
     *
     * Example:
     *
     * ```jsx
     *   var App = React.createClass({
     *       render: function () {
     *           return (
     *               <Draggable grid={[25, 25]}>
     *                   <div>I snap to a 25 x 25 grid</div>
     *               </Draggable>
     *           );
     *       }
     *   });
     * ```
     */
    grid: React.PropTypes.arrayOf(React.PropTypes.number),

    /**
     * `start` specifies the x and y that the dragged item should start at
     *
     * Example:
     *
     * ```jsx
     *   var App = React.createClass({
     *       render: function () {
     *           return (
     *               <Draggable start={{x: 25, y: 25}}>
     *                   <div>I start with left: 25px; top: 25px;</div>
     *               </Draggable>
     *           );
     *       }
     *   });
     * ```
     */
    start: React.PropTypes.object,

    /**
     * Called when dragging starts.
     *
     * Example:
     *
     * ```js
     *  function (event, ui) {}
     * ```
     *
     * `event` is the Event that was triggered.
     * `ui` is an object:
     *
     * ```js
     *  {
     *    position: {top: 0, left: 0}
     *  }
     * ```
     */
    onStart: React.PropTypes.func,

    /**
     * Called while dragging.
     *
     * Example:
     *
     * ```js
     *  function (event, ui) {}
     * ```
     *
     * `event` is the Event that was triggered.
     * `ui` is an object:
     *
     * ```js
     *  {
     *    position: {top: 0, left: 0}
     *  }
     * ```
     */
    onDrag: React.PropTypes.func,

    /**
     * Called when dragging stops.
     *
     * Example:
     *
     * ```js
     *  function (event, ui) {}
     * ```
     *
     * `event` is the Event that was triggered.
     * `ui` is an object:
     *
     * ```js
     *  {
     *    position: {top: 0, left: 0}
     *  }
     * ```
     */
    onStop: React.PropTypes.func,

    /**
     * A workaround option which can be passed if
     * onMouseDown needs to be accessed,
     * since it'll always be blocked (due to that
     * there's internal use of onMouseDown)
     *
     */
    onMouseDown: React.PropTypes.func,

    /**
     * Defines the bounderies around the element
     * could be dragged. This property could be
     * object or a string. If used as object
     * the bounderies should be defined as:
     *
     * {
     *   left: LEFT_BOUND,
     *   right: RIGHT_BOUND,
     *   top: TOP_BOUND,
     *   bottom: BOTTOM_BOUND
     * }
     *
     * The only acceptable string
     * property is: "parent".
     */
    bound: React.PropTypes.any
  },

  componentWillUnmount: function () {
    // Remove any leftover event handlers
    removeEvent(window, dragEventFor.move, this.handleDrag);
    removeEvent(window, dragEventFor.end, this.handleDragEnd);
  },

  getDefaultProps: function () {
    return {
      axis: 'both',
      handle: null,
      cancel: null,
      grid: null,
      bound: false,
      start: {
        x: 0,
        y: 0
      },
      onStart: emptyFunction,
      onDrag: emptyFunction,
      onStop: emptyFunction,
      onMouseDown: emptyFunction
    };
  },

  getInitialState: function () {
    return {
      // Whether or not currently dragging
      dragging: false,

      // Start top/left of this.getDOMNode()
      startX: 0,
      startY: 0,

      // Offset between start top/left and mouse top/left
      offsetX: 0,
      offsetY: 0,

      // Current top/left of this.getDOMNode()
      pageX: this.props.start.x,
      pageY: this.props.start.y
    };
  },

  handleDragStart: function (e) {
    // todo: write right implementation to prevent multitouch drag
    // prevent multi-touch events
    // if (isMultiTouch(e)) {
    //     this.handleDragEnd.apply(e, arguments);
    //     return
    // }

    // Make it possible to attach event handlers on top of this one
    this.props.onMouseDown(e);

    var node = findDOMNode(this);

    // Short circuit if handle or cancel prop was provided
    // and selector doesn't match
    if ((this.props.handle && !matchesSelector(e.target, this.props.handle)) ||
      (this.props.cancel && matchesSelector(e.target, this.props.cancel))) {
      return;
    }

    var dragPoint = getControlPosition(e);

    // Initiate dragging
    this.setState({
      dragging: true,
      offsetX: parseInt(dragPoint.pageX, 10),
      offsetY: parseInt(dragPoint.pageY, 10),
      startX: parseInt(node.style.left, 10) || 0,
      startY: parseInt(node.style.top, 10) || 0
    });

    // Call event handler
    this.props.onStart(e, createUIEvent(this));

    // Add event handlers
    addEvent(window, dragEventFor.move, this.handleDrag);
    addEvent(window, dragEventFor.end, this.handleDragEnd);
  },

  handleDragEnd: function (e) {
    // Short circuit if not currently dragging
    if (!this.state.dragging) {
      return;
    }

    // Turn off dragging
    this.setState({
      dragging: false
    });

    // Call event handler
    this.props.onStop(e, createUIEvent(this));

    // Remove event handlers
    removeEvent(window, dragEventFor.move, this.handleDrag);
    removeEvent(window, dragEventFor.end, this.handleDragEnd);
  },

  handleDrag: function (e) {
    var dragPoint = getControlPosition(e);

    // Calculate top and left
    var pageX = (this.state.startX +
        (dragPoint.pageX - this.state.offsetX));
    var pageY = (this.state.startY +
        (dragPoint.pageY - this.state.offsetY));
    var pos =
      getBoundPosition(pageX, pageY, this.props.bound, findDOMNode(this));
    pageX = pos.pageX;
    pageY = pos.pageY;

    // Snap to grid if prop has been provided
    if (Array.isArray(this.props.grid)) {
      var directionX = pageX < parseInt(this.state.pageX, 10) ? -1 : 1;
      var directionY = pageY < parseInt(this.state.pageY, 10) ? -1 : 1;

      pageX = Math.abs(pageX - parseInt(this.state.pageX, 10)) >=
          this.props.grid[0]
          ? (parseInt(this.state.pageX, 10) +
            (this.props.grid[0] * directionX))
          : this.state.pageX;

      pageY = Math.abs(pageY - parseInt(this.state.pageY, 10)) >=
          this.props.grid[1]
          ? (parseInt(this.state.pageY, 10) +
            (this.props.grid[1] * directionY))
          : this.state.pageY;
    }

    // Update top and left
    this.setState({
      pageX: pageX,
      pageY: pageY
    });

    // Call event handler
    this.props.onDrag(e, createUIEvent(this));

    // Prevent the default behavior
    e.preventDefault();
  },

  render: function () {
    var style = {
      // Set top if vertical drag is enabled
      top: canDragY(this)
        ? this.state.pageY
        : this.state.startY,

      // Set left if horizontal drag is enabled
      left: canDragX(this)
        ? this.state.pageX
        : this.state.startX
    };

    var className = CX({
      'react-drag': true,
      'react-drag-dragging': this.state.dragging
    });
    var oldClass = this.props.children.props.className;
    if (oldClass) {
      className = oldClass + ' ' + className;
    }
    // Reuse the child provided
    // This makes it flexible to use whatever element is wanted (div, ul, etc)
    return React.cloneElement(
        React.Children.only(this.props.children), {
      style: style,
      className: className,

      onMouseDown: this.handleDragStart,
      onTouchStart: function (ev) {
        ev.preventDefault(); // prevent for scroll
        return this.handleDragStart.apply(this, arguments);
      }.bind(this),

      onMouseUp: this.handleDragEnd,
      onTouchEnd: this.handleDragEnd
    });
  }
});

module.exports = ReactDrag;


}).call(this,typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
},{}]},{},[1])(1)
});