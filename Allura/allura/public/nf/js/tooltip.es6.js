/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/
'use strict';


/**
 * React Tooltip (tooltipster) Base class

 * @constructor
 */
class ToolTip extends React.Component {
    constructor(props) {
        super(props);
    }

    componentDidMount() {
        var _this = this;
        $(".tooltip-link").tooltipster({
            animation: _this.props.animation,
            speed: _this.props.speed,
            delay: _this.props.delay,
            theme: _this.props.theme,
            contentAsHTML: _this.props.contentAsHTML,
            trigger: _this.props.trigger,
            position: _this.props.position,
            multiple: _this.props.multiple,
            iconCloning: false,
            maxWidth: this.props.maxWidth
        }).focus(function () {
            $(this).tooltipster('show');
        }).blur(function () {
            $(this).tooltipster('hide');
        });
    }

}
ToolTip.propTypes = {
    animation: React.PropTypes.string,
    speed: React.PropTypes.number,
    position: React.PropTypes.string,
    contentAsHTML: React.PropTypes.bool,
    delay: React.PropTypes.number,
    theme: React.PropTypes.string,
    maxWidth: React.PropTypes.number,
    trigger: React.PropTypes.string,
    multiple: React.PropTypes.bool,
    classes: React.PropTypes.array,
    text: React.PropTypes.string.isRequired,
    href: React.PropTypes.string.isRequired,
    toolTip: React.PropTypes.string
};

ToolTip.defaultProps = {
    animation: 'fade',
    speed: 150,
    delay: 0,
    maxWidth: 300,
    multiple: false,
    contentAsHTML: false,
    position: 'left',
    trigger: 'hover',
    theme: 'tooltipster-light'
};

/**
 * Tooltip Link

 * @constructor
 */
class ToolTipLink extends ToolTip {
    constructor(props) {
        super(props);
    }

    render() {
        var classes = this.props.classes.join(' ') + " tooltip-link";
        return <a href={this.props.href} className={classes} title={this.props.toolTip}>{this.props.text}</a>
    }
}