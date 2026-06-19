/** 通用区块容器 */
export default function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--color-paper-2)',
      border: '1px solid var(--color-rule)',
      borderRadius: 'var(--radius-md)',
      padding: 20,
      marginBottom: 20,
    }}>
      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 15,
        fontWeight: 700,
        color: 'var(--color-ink)',
        marginBottom: 14,
      }}>
        {title}
      </h3>
      {children}
    </div>
  );
}
