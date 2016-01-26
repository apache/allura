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

/* exported ToolTip */
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
        $(this.props.targetSelector).tooltipster({
            animation: _this.props.animation,
            speed: _this.props.speed,
            delay: _this.props.delay,
            theme: _this.props.theme,
            contentAsHTML: _this.props.contentAsHTML,
            trigger: _this.props.trigger,
            position: _this.props.position,
            multiple: _this.props.multiple,
            iconCloning: false,
            maxWidth: _this.props.maxWidth
        });
    }

    render() {
        return null;
    }
}

ToolTip.propTypes = {
    targetSelector: React.PropTypes.string.isRequired,
    animation: React.PropTypes.string,
    speed: React.PropTypes.number,
    position: React.PropTypes.string,
    contentAsHTML: React.PropTypes.bool,
    delay: React.PropTypes.number,
    theme: React.PropTypes.string,
    maxWidth: React.PropTypes.number,
    trigger: React.PropTypes.string,
    multiple: React.PropTypes.bool,
};

ToolTip.defaultProps = {
    animation: 'fade',
    speed: 150,
    delay: 0,
    maxWidth: 300,
    multiple: true,
    contentAsHTML: false,
    position: 'left',
    trigger: 'hover',
    classes: [],
    theme: 'tooltipster-light'
};

