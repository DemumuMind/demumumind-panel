<script lang="ts">
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { getJSON, streamChat } from '$lib/api';
	import type { ChatUsage } from '$lib/api';
	import { panelKey, showToast } from '$lib/stores';
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';
	import { Play, Send, Trash2, FileDown, FileJson } from 'lucide-svelte';

	let models = $state<any[]>([]);
	let selectedModel = $state('');
	let modelFilter = $state('');
	let history = $state<{ role: string; content: string; reasoning?: string; usage?: ChatUsage; cached?: boolean }[]>([]);
	let draft = $state('');
	let busy = $state(false);
	let temperature = $state('0.7');
	let maxTokens = $state('256');
	let cacheEnabled = $state(false);

	let filteredModels = $derived(
		modelFilter
			? models.filter((m) => m.user_model_id.toLowerCase().includes(modelFilter.toLowerCase()))
			: models
	);

	onMount(async () => {
		try {
			const data = await getJSON<any>('/v1/models?limit=200&offset=0');
			models = data.items || [];
			if (models.length) selectedModel = models[0].user_model_id;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	});

	function send() {
		if (!get(panelKey)) {
			showToast('Login first', 'error');
			return;
		}
		if (!selectedModel || !draft.trim() || busy) return;
		busy = true;
		const userText = draft.trim();
		draft = '';
		const userIdx = history.length;
		history = [...history, { role: 'user', content: userText }];
		const assistantIdx = history.length;
		history = [...history, { role: 'assistant', content: '', reasoning: '' }];
		const messagesForApi = history
			.slice(0, userIdx + 1)
			.map((m) => ({ role: m.role, content: m.content }));
		const temp = cacheEnabled ? 0 : parseFloat(temperature.replace(',', '.')) || 0.7;
		const maxT = parseInt(maxTokens) || undefined;
		streamIt(messagesForApi, temp, maxT, assistantIdx);
	}

	async function streamIt(messagesForApi: any[], temp: number, maxT: number | undefined, idx: number) {
		try {
			for await (const chunk of streamChat({
				model: selectedModel,
				messages: messagesForApi,
				temperature: temp,
				max_tokens: maxT,
				...(cacheEnabled ? { stream_options: { include_usage: true } } : {})
			})) {
				if (chunk.content) history[idx].content += chunk.content;
				if (chunk.reasoning) history[idx].reasoning = (history[idx].reasoning || '') + chunk.reasoning;
				if (chunk.usage) history[idx].usage = chunk.usage;
				if (chunk.cached) history[idx].cached = true;
			}
		} catch (e: any) {
			history[idx].content = `Error: ${e.message}`;
		} finally {
			busy = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function clearChat() {
		history = [];
		draft = '';
		busy = false;
	}

	function download(filename: string, content: string, mime: string) {
		const blob = new Blob([content], { type: mime });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	function exportChat(format: 'md' | 'json') {
		const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
		if (format === 'json') {
			const data = history.map((m) => ({
				role: m.role,
				content: m.content,
				reasoning: m.reasoning,
				usage: m.usage
			}));
			download(`demumumind-chat-${stamp}.json`, JSON.stringify(data, null, 2), 'application/json');
			return;
		}
		const lines: string[] = ['# DemumuMind Playground', ''];
		for (const m of history) {
			if (m.role === 'user') {
				lines.push('**User:**', '', m.content, '');
			} else {
				lines.push('**Assistant:**', '');
				if (m.reasoning) lines.push('<details><summary>Мысли</summary>', '', m.reasoning, '', '</details>', '');
				lines.push(m.content, '');
				if (m.usage) {
					const u = m.usage;
					lines.push(
						`_Usage: prompt ${u.prompt_tokens ?? '-'}, completion ${u.completion_tokens ?? '-'}, total ${u.total_tokens ?? '-'}, cached ${u.prompt_tokens_details?.cached_tokens ?? '-'}, reasoning ${u.completion_tokens_details?.reasoning_tokens ?? '-'}_`,
						''
					);
				}
				lines.push('---', '');
			}
		}
		download(`demumumind-chat-${stamp}.md`, lines.join('\n'), 'text/markdown');
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Play class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Playground</h1>
</div>

<Card class="mb-6">
	<div class="flex flex-col sm:flex-row gap-3 mb-4 items-end">
		<div class="flex-1 w-full">
			<label for="pg-model" class="text-xs text-(--text-muted) block mb-1">Model</label>
			<Select id="pg-model" bind:value={selectedModel}>
				{#each filteredModels as m}
					<option value={m.user_model_id}>{m.user_model_id} ({m.provider?.name})</option>
				{/each}
			</Select>
			<Input id="pg-filter" type="text" placeholder="Фильтр моделей…" bind:value={modelFilter} class="mt-2" />
		</div>
		<div class="w-full sm:w-24">
			<label for="pg-temp" class="text-xs text-(--text-muted) block mb-1">Temp</label>
			<Input id="pg-temp" type="text" bind:value={temperature} placeholder="0.7" />
		</div>
		<div class="w-full sm:w-24">
			<label for="pg-max" class="text-xs text-(--text-muted) block mb-1">Max tokens</label>
			<Input id="pg-max" type="number" bind:value={maxTokens} min="1" max="99999" step="1" />
		</div>
		<div class="flex items-end gap-2 pb-1">
			<label class="flex items-center gap-1 text-xs text-(--text-muted) cursor-pointer">
				<input type="checkbox" bind:checked={cacheEnabled} class="accent-(--accent)" />
				Cache
			</label>
		</div>
	</div>

	<div class="flex flex-col gap-3 mb-4 max-h-[55vh] overflow-auto">
		{#each history as msg, i}
			{#if msg.role === 'user'}
				<div class="self-end max-w-[80%] rounded-xl bg-gradient-to-br from-(--accent) to-(--accent-2) px-3 py-2 text-sm text-white whitespace-pre-wrap shadow-(--shadow-card)">
					{msg.content}
				</div>
			{:else}
				<div class="self-start max-w-[85%] rounded-xl bg-(--bg-elevated) border border-(--border) px-3 py-2 text-sm text-(--text) shadow-(--shadow-card)">
					{#if msg.cached}
						<div class="mb-1 text-xs text-emerald-400">⚡ cached (panel)</div>
					{/if}
					{#if msg.reasoning}
						<details class="mb-1">
							<summary class="cursor-pointer text-xs text-(--text-faint) select-none">Мысли</summary>
							<pre class="mt-1 whitespace-pre-wrap text-xs text-(--text-muted)">{msg.reasoning}</pre>
						</details>
					{/if}
					<div class="whitespace-pre-wrap">{msg.content || (busy && i === history.length - 1 ? '…' : '')}</div>
					{#if msg.usage}
						<details class="mt-2">
							<summary class="cursor-pointer text-xs text-(--text-faint) select-none">ⓘ Usage</summary>
							<table class="mt-1 text-xs text-(--text-muted)">
								<tbody>
									<tr><td class="pr-4">prompt_tokens</td><td class="text-right tabular-nums">{msg.usage.prompt_tokens ?? '-'}</td></tr>
									<tr><td class="pr-4">completion_tokens</td><td class="text-right tabular-nums">{msg.usage.completion_tokens ?? '-'}</td></tr>
									<tr><td class="pr-4">total_tokens</td><td class="text-right tabular-nums">{msg.usage.total_tokens ?? '-'}</td></tr>
									<tr><td class="pr-4">cached_tokens</td><td class="text-right tabular-nums">{msg.usage.prompt_tokens_details?.cached_tokens ?? '-'}</td></tr>
									<tr><td class="pr-4">reasoning_tokens</td><td class="text-right tabular-nums">{msg.usage.completion_tokens_details?.reasoning_tokens ?? '-'}</td></tr>
								</tbody>
							</table>
						</details>
					{/if}
				</div>
			{/if}
		{/each}
		{#if history.length === 0}
			<p class="text-center text-(--text-faint) text-sm py-6">Напиши сообщение, чтобы начать чат</p>
		{/if}
	</div>

	<div class="flex gap-2 items-end flex-wrap">
		<textarea
			class="flex-1 min-w-[200px] rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text) placeholder:text-(--text-faint) focus:outline-none focus:ring-2 focus:ring-(--accent)/40 focus:border-(--accent)"
			rows={2}
			placeholder="Сообщение… (Enter — отправить)"
			bind:value={draft}
			onkeydown={onKeydown}
		></textarea>
		<Button onclick={send} disabled={busy || !draft.trim() || !selectedModel}><Send class="w-4 h-4" /> {busy ? '…' : 'Send'}</Button>
		<Button variant="secondary" onclick={clearChat} disabled={history.length === 0}><Trash2 class="w-4 h-4" /></Button>
		<Button variant="secondary" onclick={() => exportChat('md')} disabled={history.length === 0}><FileDown class="w-4 h-4" /></Button>
		<Button variant="secondary" onclick={() => exportChat('json')} disabled={history.length === 0}><FileJson class="w-4 h-4" /></Button>
	</div>
</Card>