/** 通用区块容器 */
export default function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--r-md)',
      padding: 20,
      marginBottom: 20,
    }}>
      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 15,
        fontWeight: 700,
        color: 'var(--ink-100)',
        marginBottom: 14,
      }}>
        {title}
      </h3>
      {children}
    </div>
  );
}
