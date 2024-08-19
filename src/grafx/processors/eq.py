import torch.nn as nn

from grafx.processors.core.convolution import convolve
from grafx.processors.core.fir import ZeroPhaseFilterBankFIR, ZeroPhaseFIR
from grafx.processors.core.geq import GraphicEqualizerBiquad
from grafx.processors.core.iir import BiquadFilterBackend
from grafx.processors.core.midside import lr_to_ms, ms_to_lr


class ZeroPhaseFIREqualizer(nn.Module):
    r"""
    A single-channel zero-phase finite impulse response (FIR) filter :cite:`smith2007introduction, smith2011spectral, engel2020ddsp`.

        From the input log-magnitude $H_{\mathrm{log}}$,
        we compute inverse FFT (IFFT) of the magnitude response
        and multiply it with a zero-centered window $v[n]$.
        Each input channel is convolved with the following FIR.
        $$
        h[n] = v[n] \cdot \frac{1}{N} \sum_{k=0}^{N-1} \exp H_{\mathrm{log}}[k] \cdot  w_{N}^{kn}.
        $$

        Here, $-(N+1)/2 \leq n \leq (N+1)/2$ and $w_{N} = \exp(j\cdot 2\pi/N)$.
        This equalizer's learnable parameter is $p = \{ H_{\mathrm{log}} \}$.

    Args:
        num_magnitude_bins (:python:`int`, *optional*):
            The number of FFT magnitude bins (default: :python:`1024`).
        window (:python:`str` or :python:`FloatTensor`, *optional*):
            The window function to use for the FIR filter.
            If :python:`str` is given, we create the window internally.
            It can be: :python:`"hann"`, :python:`"hamming"`, :python:`"blackman"`, :python:`"bartlett"`, and :python:`"kaiser"`.
            If :python:`FloatTensor` is given, we use it as a window (default: :python:`"hann"`).
        **window_kwargs (:python:`Dict[str, Any]`, *optional*):
            Additional keyword arguments for the window function.
    """

    def __init__(self, num_magnitude_bins=1024):
        super().__init__()
        self.num_magnitude_bins = num_magnitude_bins
        self.fir = ZeroPhaseFIR(num_magnitude_bins)

    def forward(self, input_signals, log_magnitude):
        r"""
        Processes input audio with the processor and given parameters.

        Args:
            input_signals (:python:`FloatTensor`, :math:`B \times C \times L`):
                A batch of input audio signals.
            log_magnitude (:python:`FloatTensor`, :math:`B \times K \:\!`):
                A batch of log-magnitude vectors of the FIR filter.

        Returns:
            :python:`FloatTensor`: A batch of output signals of shape :math:`B \times C \times L`.
        """
        fir = self.fir(log_magnitude)[:, None, :]
        output_signals = convolve(input_signals, fir, mode="zerophase")
        return output_signals

    def parameter_size(self):
        r"""
        Returns:
            :python:`Dict[str, Tuple[int, ...]]`: A dictionary that contains each parameter tensor's shape.
        """
        return {"log_magnitude": self.num_magnitude_bins}


class NewZeroPhaseFIREqualizer(nn.Module):
    r"""
    A single-channel zero-phase finite impulse response (FIR) filter :cite:`smith2007introduction, smith2011spectral, engel2020ddsp`.

        From the input log-magnitude $H_{\mathrm{log}}$,
        we compute inverse FFT (IFFT) of the magnitude response
        and multiply it with a zero-centered window $w[n]$.
        Each input channel is convolved with the following FIR.
        $$
        h[n] = w[n] \cdot \frac{1}{N} \sum_{k=0}^{N-1} \exp H_{\mathrm{log}}[k] \cdot  z_{N}^{kn}.
        $$

        Here, $-(N+1)/2 \leq n \leq (N+1)/2$ and $z_{N} = \exp(j\cdot 2\pi/N)$.
        This equalizer's learnable parameter is $p = \{ H_{\mathrm{log}} \}$.

        From the input log-energy $H_{\mathrm{fb}} \in \mathbb{R}^{K_{\mathrm{fb}}}$,
        we compute the FFT magnitudes as
        $$
        H_{\mathrm{log}} = \sqrt { M \exp (H_{\mathrm{fb}}) + \epsilon}
        $$

        where $M \in \mathbb{R}^{K \times K_{\mathrm{fb}}}$ is the filterbank matrix
        ($K$ and $K_{\mathrm{fb}}$ are the number of FFT magnitude bins and filterbank bins, respectively).
        We use the standard triangular filterbank.
        After obtaining the log-magnitude response, the remaining process is the same as :class:`~grafx.processors.eq.ZeroPhaseFIREqualizer`.
        This equalizer's learnable parameter is $p = \{ H_{\mathrm{fb}} \}$.

    Args:
        n_frequency_bins (:python:`int`, *optional*):
            The number of FFT energy bins (default: :python:`1024`).
        eq_channel (:python:`str`, *optional*):
            The channel configuration of the equalizer,
            which can be :python:`"mono"`, :python:`"stereo"`, :python:`"midside"`, or :python:`"pseudo_midside"`
            (default: :python:`"mono"`).
        use_filterbank (:python:`bool`, *optional*):
            Whether to use the filterbank (default: :python:`False`).
        scale (:python:`str`, *optional*):
            The frequency scale to use, which can be:
            :python:`"bark_traunmuller"`, :python:`"bark_schroeder"`, :python:`"bark_wang"`,
            :python:`"mel_htk"`, :python:`"mel_slaney"`, :python:`"linear"`, and :python:`"log"`
            (default: :python:`"bark_traunmuller"`).
        n_filters (:python:`int`, *optional*):
            Number of filterbank bins (default: :python:`80`).
        f_min (:python:`float`, *optional*):
            Minimum frequency in Hz. (default: :python:`40`).
        f_max (:python:`float` or :python:`None`, *optional*):
            Maximum frequency in Hz.
            If :python:`None`, the sampling rate :python:`sr` must be provided
            and we use the half of the sampling rate (default: :python:`None`).
        sr (:python:`float` or :python:`None`, *optional*):
            The underlying sampling rate. Only used when using the filterbank
            (default: :python:`None`).
        window (:python:`str` or :python:`FloatTensor`, *optional*):
            The window function to use for the FIR filter.
            If :python:`str` is given, we create the window internally.
            It can be: :python:`"hann"`, :python:`"hamming"`, :python:`"blackman"`, :python:`"bartlett"`, and :python:`"kaiser"`.
            If :python:`FloatTensor` is given, we use it as a window (default: :python:`"hann"`).
        **window_kwargs (:python:`Dict[str, Any]`, *optional*):
            Additional keyword arguments for the window function.
    """

    def __init__(
        self,
        n_frequency_bins=1024,
        eq_channel="mono",
        use_filterbank=False,
        scale="bark_traunmuller",
        n_filters=80,
        f_min=40,
        f_max=None,
        sr=None,
        eps=1e-7,
        window="hann",
        **window_kwargs,
    ):
        super().__init__()
        self.n_frequency_bins = n_frequency_bins
        self.n_filters = n_filters
        self.eq_channel = eq_channel
        self.eps = eps
        if use_filterbank:
            self.fir = ZeroPhaseFilterBankFIR(
                num_energy_bins=n_frequency_bins,
                scale=scale,
                n_filters=n_filters,
                f_min=f_min,
                f_max=f_max,
                sr=sr,
                window=window,
                **window_kwargs,
            )
        else:
            self.fir = ZeroPhaseFIR(n_frequency_bins, window, **window_kwargs)

        match self.eq_channel:
            case "mono" | "stereo":
                self.process = self._process_mono_stereo
            case "midside":
                self.process = self._process_midside
            case "pseudo_midside":
                self.process = self._process_pseudo_midside

    def forward(self, input_signals, log_magnitude):
        r"""
        Processes input audio with the processor and given parameters.

        Args:
            input_signals (:python:`FloatTensor`, :math:`B \times C \times L`):
                A batch of input audio signals.
            log_magnitude (:python:`FloatTensor`, :math:`B \times C_\mathrm{eq} \times K` *or* :math:`B \times C_\mathrm{eq} \times K_\mathrm{fb}`):
                A batch of log-magnitude vectors of the FIR filter.

        Returns:
            :python:`FloatTensor`: A batch of output signals of shape :math:`B \times C \times L`.
        """
        fir = self.fir(log_magnitude)
        output_signals = self.process(input_signals, fir)
        return output_signals

    def parameter_size(self):
        r"""
        Returns:
            :python:`Dict[str, Tuple[int, ...]]`: A dictionary that contains each parameter tensor's shape.
        """
        n_bins = self.n_filters if self.use_filterbank else self.n_frequency_bins
        match self.eq_channel:
            case "mono":
                n_channels = 1
            case "stereo" | "midside":
                n_channels = 2
        return {"log_energy": (n_channels, n_bins)}

    def _process_mono_stereo(self, input_signals, fir):
        return convolve(input_signals, fir, mode="zerophase")

    def _process_midside(self, input_signals, fir):
        input_signals = lr_to_ms(input_signals)
        output_signals = convolve(input_signals, fir, mode="zerophase")
        return ms_to_lr(output_signals)

    def _process_pseudo_midside(self, input_signals, fir):
        fir = ms_to_lr(fir)
        return convolve(input_signals, fir, mode="zerophase")


class ParametricEqualizer(nn.Module):
    r"""
    A parametric equalizer (PEQ) based on second-order filters.
    """


class GraphicEqualizer(nn.Module):
    r"""
    A graphic equalizer (GEQ) based on second-order peaking filters :cite:`liski2017quest`.

        We cascade $K$ biquad filters to form a graphic equalizer,
        whose transfer function is given as $H(z) = \prod_{k=1}^{K} H_k(z)$ where each biquad $H_k(z)$ is as follows,
        $$
        H_k(z)=\frac{1+g_k \beta_k-2 \cos (\omega_k) z^{-1}+(1-g_k \beta_k) z^{-2}}{1+\beta_k-2 \cos (\omega_k) z^{-1}+(1-\beta_k) z^{-2}}.
        $$

        Here, $g_k$ is the linear gain and $\omega_k$ is the center frequency.
        $\beta_k$ is given as
        $$
        \beta_k = \sqrt{\frac{\left|\tilde{g}_k^2-1\right|}{\left|g_k^2-\tilde{g}_k^2\right|}} \tan {\frac{B_k}{2}}
        $$

        where $B_k$ is the bandwidth frequency and $\tilde{g}_k$ is the gain at the neighboring band frequency,
        pre-determined to be $\tilde{g}_k = g_k^{0.4}$.
        The frequency values ($\omega_k$ and $B_k$) and the number of bands $K$ are also determined by the frequency scale.
        The learnable parameter is a concatenation of the log-magnitudes, i.e., $\smash{p = \{ \mathbf{g}^{\mathrm{log}} \}}$ where $\smash{g_k = \exp g_k^{\mathrm{log}}}$.

        Note that the log-gain parameters are different to the equalizer's log-magnitude response values at the center frequencies known as "control points".
        To set the log-gains to match the control points, we can use least-square optimization methods :cite:`liski2017quest, valimaki2019neurally`.


    Args:
        scale (:python:`str`, *optional*):
            The frequency scale to use, which can be:
            24-band :python:`"bark"` and 31-band :python:`"third_oct"` (default: :python:`"bark"`).
        sr (:python:`int`, *optional*):
            The underlying sampling rate of the input signal (default: :python:`44100`).
        backend (:python:`str`, *optional*):
            The backend to use for the filtering, which can either be the frequency-sampling method
            :python:`"fsm"` or exact time-domain filter :python:`"lfilter"` (default: :python:`"fsm"`).
        fsm_fir_len (:python:`int`, *optional*):
            The length of FIR approximation when :python:`backend == "fsm"` (default: :python:`8192`).
    """

    def __init__(
        self,
        scale="bark",
        sr=44100,
        backend="fsm",
        fsm_fir_len=8192,
    ):
        super().__init__()
        self.geq = GraphicEqualizerBiquad(scale=scale, sr=sr)
        self.biquad = BiquadFilterBackend(backend=backend, fsm_fir_len=fsm_fir_len)

    def forward(self, input_signal, log_gains):
        r"""
        Processes input audio with the processor and given parameters.

        Args:
            input_signal (:python:`FloatTensor`, :math:`B \times C \times L`):
                A batch of input audio signals.
            log_gains (:python:`FloatTensor`, :math:`B \times K \:\!`):
                A batch of log-gain vectors of the GEQ.

        Returns:
            :python:`FloatTensor`: A batch of output signals of shape :math:`B \times C \times L`.
        """
        Bs, As = self.geq(log_gains)
        output_signal = self.biquad(input_signal, Bs, As)
        return output_signal

    def parameter_size(self):
        r"""
        Returns:
            :python:`Dict[str, Tuple[int, ...]]`: A dictionary that contains each parameter tensor's shape.
        """
        num_bands = self.geq.num_bands
        channel = 2
        return {"log_gains": (channel, num_bands)}
