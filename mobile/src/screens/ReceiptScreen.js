import React from 'react';
import { Linking, ScrollView, Text, View } from 'react-native';
import { receiptUrl } from '../api';
import { Btn, C, Card, H1, Muted, Notice, money, s } from '../ui';

export default function ReceiptScreen({ route, navigation }) {
  const { order } = route.params;
  const p = order.receipt.payload;
  const open = () => Linking.openURL(receiptUrl(order.order_id));
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad}>
      <Notice kind="ok" text="Payment successful. Thank you!" />
      <Card>
        <H1>Receipt</H1>
        <Muted>Order {p.order_id}</Muted>
        <Muted>Paid {p.paid_at}</Muted>
        {p.items.map((i) => (
          <View key={i.variant_id} style={[s.row, { justifyContent: 'space-between', paddingVertical: 8 }]}>
            <Text style={{ fontSize: 16, color: C.text }}>{i.variant_id} × {i.quantity}</Text>
            <Text style={{ fontSize: 16, color: C.text }}>{money(i.unit_price_minor * i.quantity)}</Text>
          </View>
        ))}
        <Text style={{ fontSize: 16, color: C.text }}>Subtotal: {money(p.subtotal_minor)}</Text>
        <Text style={{ fontSize: 16, color: C.text }}>Discount: −{money(p.discount_minor)}</Text>
        <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, marginTop: 8 }}>Total: {money(p.total_minor)}</Text>
        <Muted style={{ marginTop: 8 }}>Payment {order.payment.state} · {order.payment.capture_id}</Muted>
        <Muted>Signature {order.receipt.signature.slice(0, 16)}…</Muted>
      </Card>
      <Btn title="Download PDF receipt" onPress={open} />
      <Btn title="Back to store" kind="secondary" onPress={() => navigation.goBack()} />
    </ScrollView>
  );
}
