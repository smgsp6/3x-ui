package tgbot

import (
	"strings"
	"testing"

	"github.com/mhsanaei/3x-ui/v3/internal/eventbus"
)

func TestVelaEventNotificationsNeverSerializePrivateFields(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	const secret = "PRIVATE_TOKEN_001"
	const ip = "203.0.113.73"
	const email = "private.client@example.invalid"
	for _, typ := range []eventbus.EventType{
		eventbus.EventOutboundDown,
		eventbus.EventOutboundUp,
		eventbus.EventXrayCrash,
		eventbus.EventNodeDown,
		eventbus.EventNodeUp,
		eventbus.EventCPUHigh,
		eventbus.EventMemoryHigh,
		eventbus.EventLoginAttempt,
	} {
		t.Run(string(typ), func(t *testing.T) {
			e := eventbus.Event{
				Type: typ,
				Source: ip + " " + secret,
				Data: &eventbus.LoginEventData{
					Username: email,
					IP: ip,
					Time: secret,
					Reason: secret,
					Status: "fail",
				},
			}
			if typ == eventbus.EventOutboundDown {
				e.Data = &eventbus.OutboundHealthData{Error: secret}
			}
			if typ == eventbus.EventNodeDown {
				e.Data = &eventbus.NodeHealthData{XrayError: secret}
			}
			msg := (&Tgbot{}).formatEventMessage(e)
			if msg == "" {
				t.Fatal("reviewed security event unexpectedly has no notification")
			}
			kind := (&Tgbot{}).eventNoticeKind(e)
			for _, private := range []string{secret, ip, email} {
				if strings.Contains(msg, private) || strings.Contains(kind, private) {
					t.Fatal("Telegram event notification exposed private telemetry")
				}
			}
		})
	}
}

func TestVelaUnknownEventIsSilenced(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	e := eventbus.Event{Type: eventbus.EventType("future.private.payload"), Source: "do-not-send"}
	if (&Tgbot{}).formatEventMessage(e) != "" {
		t.Fatal("unknown event payloads must not reach Telegram")
	}
}
