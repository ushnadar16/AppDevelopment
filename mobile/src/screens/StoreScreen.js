import React, { useCallback, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { newId } from '../storage';
import { Btn, C, Card, Chip, Empty, Field, H1, H2, Loading, Muted, Notice, money, s } from '../ui';

const CARDS = [['tok_success', 'Test card — succeeds'], ['tok_declined', 'Test card — declined'],
  ['tok_capture_fail', 'Test card — capture fails']];

export default function StoreScreen({ navigation }) {
  const { online, session } = useApp();
  const [products, setProducts] = useState(null);
  const [variant, setVariant] = useState(null);
  const [cart, setCart] = useState({});
  const [code, setCode] = useState('');
  const [card, setCard] = useState('tok_success');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    getCached('/api/v1/products').then((r) => setProducts(r.data.products)).catch((e) => setMsg(['bad', errorText(e)]));
  }, []);
  useFocusEffect(load);

  const all = (products || []).flatMap((p) => p.variants.map((v) => ({ ...v, name: p.name })));
  const lines = Object.entries(cart).map(([vid, q]) => ({ ...all.find((v) => v.variant_id === vid), quantity: q }));
  const subtotal = lines.reduce((t, l) => t + l.price_minor * l.quantity, 0);

  const add = () => {
    if (!variant) { setMsg(['warn', 'Choose a size first.']); return; }
    setCart({ ...cart, [variant]: Math.min(10, (cart[variant] || 0) + 1) });
    setMsg(['ok', 'Added to cart.']);
  };

  const pay = () => {
    Alert.alert('Confirm payment', `Pay ${money(subtotal)}${code ? ' (before discount)' : ''} with "${CARDS.find((c) => c[0] === card)[1]}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Pay', onPress: doPay },
    ]);
  };

  const doPay = async () => {
    setBusy(true); setMsg(null);
    try {
      const order = await api.checkout({
        order_id: newId('ord'), customer_id: session.user.user_id,
        items: lines.map((l) => ({ variant_id: l.variant_id, quantity: l.quantity })),
        discount_code: code.trim() ? code.trim().toUpperCase() : null, payment: { token: card },
      });
      setCart({}); setCode('');
      load();
      navigation.navigate('Receipt', { order });
    } catch (e) { setMsg(['bad', errorText(e)]); load(); } finally { setBusy(false); }
  };

  if (!products) return msg ? <Notice kind={msg[0]} text={msg[1]} /> : <Loading text="Loading store…" />;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad} keyboardShouldPersistTaps="handled">
      {products.length === 0 ? <Empty text="The store has no products yet." /> : null}
      {products.map((p) => (
        <Card key={p.product_id}>
          <View style={{ height: 120, borderRadius: 10, backgroundColor: '#E0E7FF', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}
            accessible accessibilityLabel={`${p.name} product image`}>
            <Text style={{ fontSize: 48 }}>👕</Text>
          </View>
          <H1>{p.name}</H1>
          <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, marginBottom: 8 }}>{money(p.variants[0].price_minor)}</Text>
          <Muted style={{ marginBottom: 6 }}>Size</Muted>
          <View style={s.wrap}>
            {p.variants.map((v) => (
              <Chip key={v.variant_id} label={`${v.size}${v.stock === 0 ? ' (sold out)' : ` (${v.stock} left)`}`}
                selected={variant === v.variant_id} onPress={() => v.stock > 0 && setVariant(v.variant_id)} />
            ))}
          </View>
          <Btn title="Add to cart" onPress={add} />
        </Card>
      ))}
      {msg ? <Notice kind={msg[0]} text={msg[1]} /> : null}
      <Card>
        <H2>Cart</H2>
        {lines.length === 0 ? <Muted>Your cart is empty. Pick a size and tap "Add to cart".</Muted> : lines.map((l) => (
          <View key={l.variant_id} style={[s.row, { justifyContent: 'space-between', paddingVertical: 8 }]}>
            <Text style={{ fontSize: 16, color: C.text, flex: 1 }}>{l.name} · {l.size} × {l.quantity}</Text>
            <Btn small kind="secondary" title="Remove" onPress={() => { const c = { ...cart }; delete c[l.variant_id]; setCart(c); }} />
          </View>
        ))}
        {lines.length ? <>
          <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginVertical: 8 }}>Subtotal: {money(subtotal)}</Text>
          <Field label="Discount code (optional)" value={code} onChangeText={setCode} autoCapitalize="characters" placeholder="WELCOME10" />
          <Muted style={{ marginBottom: 6 }}>Payment method (mock gateway)</Muted>
          <View style={s.wrap}>{CARDS.map(([t, l]) => <Chip key={t} label={l} selected={card === t} onPress={() => setCard(t)} />)}</View>
          {!online ? <Notice kind="warn" text="You're offline. Payments need a connection." /> : null}
          <Btn title={busy ? 'Processing payment…' : `Pay ${money(subtotal)}`} onPress={pay} disabled={busy || !online} />
        </> : null}
      </Card>
    </ScrollView>
  );
}
