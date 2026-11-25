import { describe, expect, it } from 'vitest';
import { humanStatus, t } from '../i18n';

describe('localization', () => {
  it('translates navigation, labels and workflow statuses in both supported languages', () => {
    expect(t('en', 'purchaseOrders')).toBe('Purchase Orders');
    expect(t('ja', 'purchaseOrders')).toBe('発注書');
    expect(humanStatus('en', 'IN_TRANSIT')).toBe('In Transit');
    expect(humanStatus('ja', 'IN_TRANSIT')).toBe('輸送中');
  });
});
