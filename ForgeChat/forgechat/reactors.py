from allura.lib.decorators import audit

@audit('forgechat.received_msg')
def received_msg(routing_key, data):
    pass

@audit('forgechat.send_msg')
def send_msg(routing_key, data):
    pass
